#!/usr/bin/env python3
"""
视频合成器 - 根据 timeline.json 剪辑视频、添加配音和字幕
"""

import os
import json
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed


class SRTParser:
    """SRT 字幕解析器"""
    
    @staticmethod
    def parse_srt(srt_file: str) -> List[Dict]:
        """
        解析 SRT 字幕文件
        
        Returns:
            字幕列表，每个字幕包含 index, start_time, end_time, text
        """
        subtitles = []
        
        with open(srt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 分割每个字幕块
        blocks = re.split(r'\n\s*\n', content.strip())
        
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) < 3:
                continue
            
            try:
                index = int(lines[0])
                time_line = lines[1]
                text = '\n'.join(lines[2:])
                
                # 解析时间
                match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})', time_line)
                if match:
                    start_h, start_m, start_s, start_ms = map(int, match.groups()[:4])
                    end_h, end_m, end_s, end_ms = map(int, match.groups()[4:])
                    
                    start_time = start_h * 3600 + start_m * 60 + start_s + start_ms / 1000
                    end_time = end_h * 3600 + end_m * 60 + end_s + end_ms / 1000
                    
                    subtitles.append({
                        'index': index,
                        'start_time': start_time,
                        'end_time': end_time,
                        'text': text
                    })
            except Exception as e:
                print(f"  ⚠ 解析字幕块失败: {e}")
                continue
        
        return subtitles
    
    @staticmethod
    def find_subtitle_by_line(subtitles: List[Dict], line_number: int) -> Dict:
        """
        根据行号查找字幕（SRT 中的 index）
        """
        for sub in subtitles:
            if sub['index'] == line_number:
                return sub
        return None


class VideoClipFinder:
    """视频片段查找器 - 使用 DeepSeek LLM"""
    
    def __init__(self, api_key: str = "sk-b806e7ca03ab4a9cb12445a659349268"):
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1"
        )
    
    def find_best_clip(self, narration_text: str, subtitles: List[Dict], 
                      line_start: int, line_end: int, duration: float) -> Dict:
        """
        使用 LLM 在指定行号范围内找到最匹配的视频片段
        
        Args:
            narration_text: 旁白文本
            subtitles: 原始字幕列表
            line_start: 起始行号
            line_end: 结束行号
            duration: 需要的片段时长
            
        Returns:
            最佳片段信息 {start_time, end_time, confidence, reason}
        """
        # 对齐调整：字幕的前两行不是100%对应的，所以需要 -2
        line_start_adjusted = line_start
        line_end_adjusted = line_end
        
        # 如果调整后行号为负数或0，说明对应的是字幕前两行不准确的部分，直接跳过
        if line_start_adjusted <= 0 or line_end_adjusted <= 0:
            print(f"  ⚠️ 跳过片段：调整后行号为负数 (原始: [{line_start}-{line_end}] → 调整后: [{line_start_adjusted}-{line_end_adjusted}])")
            print(f"     原因：字幕前两行不对应，无法准确匹配视频片段")
            return None
        
        # 提取范围内的字幕
        range_subs = [s for s in subtitles if line_start_adjusted <= s['index'] <= line_end_adjusted]
        
        if not range_subs:
            print(f"  ⚠ 行号范围 [{line_start_adjusted}-{line_end_adjusted}] (原始: [{line_start}-{line_end}], 已调整-2) 内没有找到字幕")
            return None
        
        # 构建上下文
        context = []
        for sub in range_subs:
            context.append(f"[{sub['index']}] {sub['start_time']:.2f}s-{sub['end_time']:.2f}s: {sub['text']}")
        
        context_text = '\n'.join(context)
        
        # 计算推荐的时长范围：音频时长 + 0.5s 到 音频时长 + 2s
        min_duration = duration + 0.5
        max_duration = duration + 2.0
        
        prompt = f"""你是一个视频剪辑专家。现在需要为以下旁白找到最匹配的视频片段。

旁白文本: {narration_text}
旁白音频时长: {duration:.2f} 秒

可选的视频片段（原始字幕）:
{context_text}

请分析这些字幕，找出最适合这段旁白的连续视频片段。要求:
1. 片段的内容要与旁白意思相关或匹配
2. **重要**: 视频片段时长必须在 {min_duration:.2f}s 到 {max_duration:.2f}s 之间（比音频稍长0.5-2秒，避免截断说话）
3. 优先选择动作性强、画面精彩的片段
4. 片段必须是连续的字幕，不能跳跃
5. 确保选择的时间区间在提供的范围内

请以 JSON 格式返回，只返回 JSON，不要其他内容:
{{
  "start_line": <起始行号>,
  "end_line": <结束行号>,
  "start_time": <开始时间（秒）>,
  "end_time": <结束时间（秒）>,
  "duration": <实际时长（秒）>,
  "confidence": <匹配度 0-1>,
  "quality_score": <质量评分 0-100>,
  "match_level": "<匹配等级: excellent|good|acceptable|poor|none>",
  "reason": "<选择理由>",
  "content_match": "<内容匹配说明>",
  "issues": ["<可能存在的问题列表>"]
}}

评分标准:
- excellent (90-100): 内容高度相关，画面精彩，时长完美
- good (70-89): 内容相关，画面合适，时长符合
- acceptable (50-69): 内容部分相关或时长稍有出入
- poor (30-49): 内容勉强相关或存在明显问题
- none (0-29): 几乎无相关内容或无法匹配
"""
        
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "你是一个专业的视频剪辑助手，擅长分析字幕并选择最佳视频片段。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # **关键修复**: 从原始字幕中获取真实的时间，而不是使用 LLM 生成的时间
            start_line = result['start_line']
            end_line = result['end_line']
            
            # 查找对应行号的字幕
            start_sub = next((s for s in range_subs if s['index'] == start_line), None)
            end_sub = next((s for s in range_subs if s['index'] == end_line), None)
            
            if not start_sub or not end_sub:
                print(f"  ⚠️ 无法找到行号 {start_line}-{end_line} 对应的字幕")
                return None
            
            # 使用字幕的真实时间
            result['start_time'] = start_sub['start_time']
            result['end_time'] = end_sub['end_time']
            result['duration'] = result['end_time'] - result['start_time']
            
            # 验证时间区间
            result = self._validate_clip_duration(result, duration, range_subs)
            
            # 获取质量评分和匹配等级
            quality_score = result.get('quality_score', 50)
            match_level = result.get('match_level', 'acceptable')
            
            # 根据匹配等级显示不同颜色的提示
            if match_level == 'excellent':
                level_icon = "\033[32m✓ 优秀\033[0m"  # 绿色
            elif match_level == 'good':
                level_icon = "\033[36m✓ 良好\033[0m"  # 青色
            elif match_level == 'acceptable':
                level_icon = "\033[33m⚠ 可接受\033[0m"  # 黄色
            elif match_level == 'poor':
                level_icon = "\033[33m⚠ 质量较差\033[0m"  # 橙色(用黄色代替)
            else:  # none
                level_icon = "\033[31m✗ 无匹配\033[0m"  # 红色
            
            print(f"  {level_icon} LLM 选择: 行 {result['start_line']}-{result['end_line']}, "
                  f"时间 {result['start_time']:.2f}s-{result['end_time']:.2f}s, "
                  f"时长 {result['duration']:.2f}s")
            print(f"    评分: {quality_score}/100 | 匹配度: {result.get('confidence', 0):.2f}")
            print(f"    内容: {result.get('content_match', result.get('reason', 'N/A'))}")
            
            # 显示可能的问题
            issues = result.get('issues', [])
            if issues and isinstance(issues, list) and len(issues) > 0:
                for issue in issues:
                    if issue and issue.strip():
                        print(f"    \033[33m⚠\033[0m {issue}")
            
            return result
            
        except Exception as e:
            print(f"  ✗ LLM 查询失败: {e}")
            # 降级策略：简单选择范围内的前几个字幕
            if range_subs:
                total_dur = 0
                selected_subs = []
                for sub in range_subs:
                    if total_dur >= duration:
                        break
                    selected_subs.append(sub)
                    total_dur += (sub['end_time'] - sub['start_time'])
                
                if selected_subs:
                    return {
                        'start_line': selected_subs[0]['index'],
                        'end_line': selected_subs[-1]['index'],
                        'start_time': selected_subs[0]['start_time'],
                        'end_time': selected_subs[-1]['end_time'],
                        'duration': selected_subs[-1]['end_time'] - selected_subs[0]['start_time'],
                        'confidence': 0.5,
                        'quality_score': 40,
                        'match_level': 'poor',
                        'reason': '降级策略：自动选择',
                        'content_match': 'LLM失败，使用自动选择策略',
                        'issues': ['LLM查询失败，无法评估匹配质量']
                    }
            return None
    
    def _validate_clip_duration(self, clip_info: Dict, audio_duration: float, 
                                range_subs: List[Dict]) -> Dict:
        """
        验证并调整视频片段时长
        
        Args:
            clip_info: LLM 返回的片段信息（已包含真实字幕时间）
            audio_duration: 音频时长
            range_subs: 可选字幕范围
            
        Returns:
            调整后的片段信息
        """
        video_duration = clip_info['duration']
        max_allowed = audio_duration + 2.0
        min_required = audio_duration + 0.5
        
        # 检查是否超过最大允许长度
        if video_duration > max_allowed:
            print(f"  ⚠️ 视频片段过长: {video_duration:.2f}s > {max_allowed:.2f}s (音频+2s)")
            
            # 截断视频：从起始行开始，找到累计时长不超过 max_allowed 的最后一行
            start_line = clip_info['start_line']
            start_time = clip_info['start_time']
            
            new_end_line = start_line
            new_end_time = start_time
            
            for sub in sorted(range_subs, key=lambda x: x['index']):
                if sub['index'] < start_line:
                    continue
                if sub['index'] > clip_info['end_line']:
                    break
                    
                # 检查如果包含这一行，总时长是否超限
                potential_duration = sub['end_time'] - start_time
                if potential_duration <= max_allowed:
                    new_end_line = sub['index']
                    new_end_time = sub['end_time']
                else:
                    break
            
            clip_info['end_line'] = new_end_line
            clip_info['end_time'] = new_end_time
            clip_info['duration'] = new_end_time - start_time
            print(f"  ✂️ 已截断至: {clip_info['duration']:.2f}s, 新行号范围: {start_line}-{new_end_line}")
        
        # 检查是否太短
        elif video_duration < min_required:
            print(f"  ⚠️ 视频片段稍短: {video_duration:.2f}s < {min_required:.2f}s (音频+0.5s)")
            
            # 尝试延长：从当前结束行往后找字幕
            start_time = clip_info['start_time']
            current_end_line = clip_info['end_line']
            
            new_end_line = current_end_line
            new_end_time = clip_info['end_time']
            
            for sub in sorted(range_subs, key=lambda x: x['index']):
                if sub['index'] <= current_end_line:
                    continue
                    
                # 检查包含这一行后的总时长
                potential_duration = sub['end_time'] - start_time
                if potential_duration <= max_allowed:
                    new_end_line = sub['index']
                    new_end_time = sub['end_time']
                    
                    # 达到最小要求就停止
                    if potential_duration >= min_required:
                        break
                else:
                    break
            
            if new_end_line > current_end_line:
                clip_info['end_line'] = new_end_line
                clip_info['end_time'] = new_end_time
                clip_info['duration'] = new_end_time - start_time
                print(f"  ➕ 已延长至: {clip_info['duration']:.2f}s, 新行号范围: {clip_info['start_line']}-{new_end_line}")
        
        return clip_info


class VideoComposer:
    """视频合成器"""
    
    def __init__(self, timeline_file: str, original_srt_file: str, 
                 original_video_file: str, api_key: str = None):
        """
        初始化视频合成器
        
        Args:
            timeline_file: timeline.json 文件路径
            original_srt_file: 原始字幕文件路径
            original_video_file: 原始视频文件路径
            api_key: DeepSeek API Key
        """
        self.timeline_file = timeline_file
        self.original_srt_file = original_srt_file
        self.original_video_file = original_video_file
        
        # 加载 timeline
        with open(timeline_file, 'r', encoding='utf-8') as f:
            self.timeline = json.load(f)
        
        # 解析原始字幕
        print(f"解析原始字幕: {original_srt_file}")
        self.subtitles = SRTParser.parse_srt(original_srt_file)
        print(f"  ✓ 共 {len(self.subtitles)} 条字幕")
        
        # 初始化 LLM
        self.clip_finder = VideoClipFinder(api_key or "sk-b806e7ca03ab4a9cb12445a659349268")
    
    def generate_video_clips(self, output_dir: str, max_workers: int = 3) -> List[Dict]:
        """
        并发生成所有视频片段
        
        Args:
            output_dir: 输出目录
            max_workers: 最大并发数（默认3）
        
        Returns:
            片段列表，每个片段包含 video_file, audio_file, subtitle_text, etc.
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        print(f"\n开始并发生成视频片段（并发数: {max_workers}）...")
        
        # 准备任务列表
        tasks = []
        for i, segment in enumerate(self.timeline['segments'], 1):
            tasks.append((i, segment, output_dir))
        
        # 并发处理
        clips = [None] * len(tasks)  # 预分配列表，保持顺序
        
        def process_one_clip(task_data):
            i, segment, output_dir = task_data
            
            print(f"\n[{i}/{len(tasks)}] 处理片段 {i}...")
            
            # 提取信息
            narration_text = segment['text']
            audio_file = segment['audio_file']
            duration = segment['duration']
            line_start = segment.get('line_range_start')
            line_end = segment.get('line_range_end')
            
            print(f"  旁白: {narration_text[:50]}...")
            print(f"  行号范围: [{line_start}-{line_end}], 时长: {duration:.2f}s")
            
            # 使用 LLM 查找最佳视频片段
            if not line_start or not line_end:
                print(f"  ⚠ 没有行号范围，跳过")
                return (i, None)
            
            clip_info = self.clip_finder.find_best_clip(
                narration_text, self.subtitles, 
                line_start, line_end, duration
            )
            
            if not clip_info:
                print(f"  ⚠ 未找到合适的视频片段，跳过")
                return (i, None)
            
            # 剪辑视频片段（一步完成：视频+配音+字幕）
            video_clip_file = os.path.join(output_dir, f'video_clip_{i:03d}.mp4')
            self._extract_video_clip(
                self.original_video_file,
                clip_info['start_time'],
                clip_info['end_time'],
                video_clip_file,
                audio_file,
                narration_text
            )
            
            # 返回片段信息
            clip_data = {
                'index': i,
                'video_file': video_clip_file,
                'audio_file': audio_file,
                'subtitle_text': narration_text,
                'video_start': clip_info['start_time'],
                'video_end': clip_info['end_time'],
                'video_duration': clip_info['duration'],
                'audio_duration': duration,
                'confidence': clip_info['confidence'],
                'reason': clip_info['reason']
            }
            
            return (i, clip_data)
        
        # 使用线程池并发执行
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_one_clip, task): task for task in tasks}
            
            for future in as_completed(futures):
                i, clip_data = future.result()
                if clip_data:
                    clips[i-1] = clip_data
        
        # 过滤掉 None
        clips = [c for c in clips if c is not None]
        
        print(f"\n✓ 并发处理完成，共生成 {len(clips)} 个视频片段")
        return clips
    
    def _extract_video_clip(self, input_video: str, start_time: float, 
                           end_time: float, output_file: str, audio_file: str, subtitle_text: str):
        """
        使用 ffmpeg 提取视频片段，并直接添加配音和字幕
        """
        duration = end_time - start_time
        
        # 创建临时字幕文件（ASS格式）
        import tempfile
        srt_file = tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8')
        srt_file.write(f"1\n00:00:00,000 --> {self._format_srt_time(duration)}\n{subtitle_text}\n")
        srt_file.close()
        
        # 一步完成：提取视频 + 添加配音 + 烧录字幕 + 调整画面
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(start_time),
            '-i', input_video,
            '-i', audio_file,
            '-t', str(duration),
            '-filter_complex',
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,subtitles={srt_file.name}:force_style='Fontsize=8,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=1,MarginV=40,Alignment=2'[vout]",
            '-map', '[vout]',
            '-map', '1:a',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '128k',
            output_file
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
            print(f"  ✓ 视频片段已保存（含配音+字幕）: {output_file}")
        except subprocess.TimeoutExpired:
            print(f"  ✗ 提取视频超时")
        except subprocess.CalledProcessError as e:
            print(f"  ✗ 提取视频失败: {e}")
            if e.stderr:
                print(f"  错误输出: {e.stderr[-500:]}")
        finally:
            # 清理临时字幕文件
            try:
                os.unlink(srt_file.name)
            except:
                pass
    
    def _format_srt_time(self, seconds: float) -> str:
        """格式化 SRT 时间"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    def compose_final_video(self, clips: List[Dict], output_file: str):
        """
        合成最终视频（直接合并所有片段，因为已经包含配音和字幕）
        """
        print(f"\n开始合成最终视频...")
        
        # 创建合并列表
        temp_dir = os.path.dirname(output_file)
        concat_file = os.path.join(temp_dir, 'concat_list.txt')
        
        with open(concat_file, 'w', encoding='utf-8') as f:
            for clip in clips:
                f.write(f"file '{clip['video_file']}'\n")
        
        # 直接合并
        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_file,
            '-c', 'copy',
            output_file
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            print(f"\n✓ 最终视频已保存: {output_file}")
        except subprocess.CalledProcessError as e:
            print(f"\n✗ 合并视频失败: {e}")
        
        # 清理
        if os.path.exists(concat_file):
            os.remove(concat_file)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='视频合成器 - 根据 timeline.json 剪辑视频')
    parser.add_argument('timeline', help='timeline.json 文件路径')
    parser.add_argument('original_srt', help='原始字幕文件路径 (如 1732974958319.srt)')
    parser.add_argument('original_video', help='原始视频文件路径')
    parser.add_argument('-o', '--output', default='final_video.mp4', help='输出视频文件路径')
    parser.add_argument('--clip-dir', default='video_clips', help='视频片段输出目录')
    parser.add_argument('-w', '--workers', type=int, default=3, help='并发数 (默认 3)')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("视频合成器")
    print("=" * 80)
    print(f"Timeline: {args.timeline}")
    print(f"原始字幕: {args.original_srt}")
    print(f"原始视频: {args.original_video}")
    print(f"输出文件: {args.output}")
    print(f"并发数: {args.workers}")
    print("=" * 80)
    
    # 创建合成器
    composer = VideoComposer(
        timeline_file=args.timeline,
        original_srt_file=args.original_srt,
        original_video_file=args.original_video
    )
    
    # 生成视频片段（并发）
    clips = composer.generate_video_clips(args.clip_dir, max_workers=args.workers)
    
    # 保存片段信息
    clips_info_file = os.path.join(args.clip_dir, 'clips_info.json')
    with open(clips_info_file, 'w', encoding='utf-8') as f:
        json.dump(clips, f, ensure_ascii=False, indent=2)
    print(f"\n✓ 片段信息已保存: {clips_info_file}")
    
    # 合成最终视频
    composer.compose_final_video(clips, args.output)
    
    print("\n" + "=" * 80)
    print("✓ 全部完成！")
    print("=" * 80)


if __name__ == "__main__":
    main()
