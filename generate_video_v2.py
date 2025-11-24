#!/usr/bin/env python3
"""
完整视频生成流程 V2：支持V2格式文案（连续文本+嵌入行号标记）
1. 解析 V2 格式文案（文本内容[行号]...）
2. 并行生成 TTS 配音（缓存）
3. 并行调用 DeepSeek 细化视频片段选择（缓存）
4. 并行提取视频片段并添加配音+字幕（缓存）
5. 合成最终视频
"""

import os
import json
import re
import hashlib
import argparse
import shutil
import time
from pathlib import Path
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI

# 导入现有模块
from video_compressor import SRTParser, VideoClipFinder
from generate_tts import parse_script as parse_tts_script
from tts_client import CosyVoiceClient
from config.cosyvoice_config import CosyVoiceConfig


class CacheManager:
    """缓存管理器"""
    
    def __init__(self, cache_dir: str = ".cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # 子目录
        self.tts_cache_dir = self.cache_dir / "tts"
        self.clip_cache_dir = self.cache_dir / "clips"
        self.meta_cache_dir = self.cache_dir / "meta"
        
        for d in [self.tts_cache_dir, self.clip_cache_dir, self.meta_cache_dir]:
            d.mkdir(exist_ok=True)
    
    def get_hash(self, content: str) -> str:
        """生成内容哈希"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def get_tts_cache_path(self, text: str, speaker: str) -> Path:
        """获取 TTS 缓存路径"""
        cache_key = f"{speaker}:{text}"
        cache_hash = self.get_hash(cache_key)
        return self.tts_cache_dir / f"{cache_hash}.wav"
    
    def get_clip_cache_path(self, clip_hash: str) -> Path:
        """获取视频片段缓存路径"""
        return self.clip_cache_dir / f"{clip_hash}.mp4"
    
    def get_meta_cache_path(self, meta_type: str, key: str) -> Path:
        """获取元数据缓存路径"""
        cache_hash = self.get_hash(key)
        return self.meta_cache_dir / f"{meta_type}_{cache_hash}.json"
    
    def save_json(self, path: Path, data: dict):
        """保存 JSON 数据"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load_json(self, path: Path) -> dict:
        """加载 JSON 数据"""
        if not path.exists():
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def clear(self):
        """清理所有缓存"""
        shutil.rmtree(self.cache_dir)
        self.__init__(str(self.cache_dir))


class ScriptParserV2:
    """V2 文案脚本解析器 - 支持连续文本+嵌入行号标记
    
    格式: 连续文本内容[行号范围]更多文本[行号范围]...
    示例: 怪盗基德[11-15]发出预告信，要偷斧江家[16-20]的两把肋差刀[21-25]...
    """
    
    @staticmethod
    def parse_script_file(script_file: str, chunk_words: int = 30) -> List[Dict]:
        """
        解析 V2 格式文案脚本文件 - 按句号和换行分割
        
        Args:
            script_file: 文案文件路径
            chunk_words: 未使用（保留参数兼容性），实际按句号/换行分割
            
        Returns:
            [{'text': '...', 'line_ranges': [[1,5], [6,10]], 'keywords': [...]}]
        """
        with open(script_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        # 先按段落分割（连续两个换行符）
        paragraphs = re.split(r'\n\s*\n', content)
        
        segments = []
        
        for paragraph in paragraphs:
            # 跳过空段落
            if not paragraph.strip():
                continue
            
            # 提取段落中的所有关键词和行号标记
            # 格式: 关键词[行号范围]
            pattern = r'([^[\]]+?)\[(\d+)-(\d+)\]'
            
            # 将段落分割成带行号标记的片段
            annotated_segments = []
            
            for match in re.finditer(pattern, paragraph):
                keyword = match.group(1).strip()
                line_start = int(match.group(2))
                line_end = int(match.group(3))
                
                if keyword:
                    annotated_segments.append({
                        'text': keyword,
                        'line_range': [line_start, line_end]
                    })
            
            # 按句号分割段落内的文本
            current_text = ""
            current_line_ranges = []
            
            for seg in annotated_segments:
                current_text += seg['text']
                current_line_ranges.append(seg['line_range'])
                
                # 检查是否遇到句号（中文或英文）
                if current_text.rstrip().endswith(('。', '.', '！', '!', '？', '?')):
                    if current_text.strip() and current_line_ranges:
                        segments.append({
                            'text': current_text.strip(),
                            'line_ranges': current_line_ranges.copy(),
                            'keywords': [s['text'] for s in annotated_segments[:len(current_line_ranges)]],
                            'line_range': [
                                min(r[0] for r in current_line_ranges),
                                max(r[1] for r in current_line_ranges)
                            ]
                        })
                    
                    # 重置
                    current_text = ""
                    current_line_ranges = []
            
            # 添加段落最后一个片段（如果没有以句号结尾）
            if current_text.strip() and current_line_ranges:
                segments.append({
                    'text': current_text.strip(),
                    'line_ranges': current_line_ranges.copy(),
                    'keywords': [s['text'] for s in annotated_segments[:len(current_line_ranges)]],
                    'line_range': [
                        min(r[0] for r in current_line_ranges),
                        max(r[1] for r in current_line_ranges)
                    ]
                })
        
        return segments


class ParallelTTSGenerator:
    """并行 TTS 生成器（带缓存）"""
    
    def __init__(self, cache_manager: CacheManager, speaker_id: str = "龙白芝", 
                 api_key: str = None, max_workers: int = 4):
        self.cache_manager = cache_manager
        self.speaker_id = speaker_id
        self.max_workers = max_workers
        
        # 从环境变量或配置文件获取 API key
        bailian_key = api_key or os.getenv("BAILIAN_API_KEY")
        if not bailian_key:
            raise ValueError(
                "BAILIAN_API_KEY is required for TTS generation. "
                "Please set the BAILIAN_API_KEY environment variable or pass --api-key argument."
            )
        
        # 初始化 TTS 客户端
        config = CosyVoiceConfig(
            api_key=bailian_key,
            speaker_id=speaker_id,
            output_dir=str(cache_manager.tts_cache_dir)
        )
        self.tts_client = CosyVoiceClient(config)
    
    def generate_one(self, segment: Dict, index: int) -> Dict:
        """生成单个 TTS 音频（带缓存）"""
        text = segment['text']
        
        # 检查缓存
        cache_path = self.cache_manager.get_tts_cache_path(text, self.speaker_id)
        
        if cache_path.exists():
            print(f"  [{index}] ✓ 使用缓存 TTS: {cache_path.name}")
            return {
                'index': index,
                'audio_file': str(cache_path),
                'text': text,
                'line_range': segment['line_range'],
                'from_cache': True
            }
        
        # 生成 TTS（带重试逻辑）
        max_retries = 3
        retry_delay = 2  # 秒
        
        for attempt in range(1, max_retries + 1):
            try:
                if attempt > 1:
                    print(f"  [{index}] 🔄 重试 {attempt}/{max_retries}...")
                    time.sleep(retry_delay)
                
                print(f"  [{index}] 🎤 生成 TTS: {text[:40]}...")
                result = self.tts_client.synthesize(text, str(cache_path))
                
                return {
                    'index': index,
                    'audio_file': str(cache_path),
                    'text': text,
                    'line_range': segment['line_range'],
                    'from_cache': False
                }
            except Exception as e:
                if attempt == max_retries:
                    print(f"  [{index}] ❌ TTS 生成失败（已重试 {max_retries} 次）: {e}")
                    return None
                else:
                    print(f"  [{index}] ⚠️  TTS 失败: {e}")
        
        return None
    
    def generate_all(self, segments: List[Dict]) -> List[Dict]:
        """并行生成所有 TTS 音频"""
        print(f"\n🎤 并行生成 TTS 音频（并发数: {self.max_workers}）...")
        
        results = [None] * len(segments)
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.generate_one, seg, i): i 
                for i, seg in enumerate(segments, 1)
            }
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results[result['index'] - 1] = result
        
        # 过滤 None
        results = [r for r in results if r is not None]
        
        cache_count = sum(1 for r in results if r.get('from_cache'))
        print(f"✅ TTS 生成完成: {len(results)} 个音频（{cache_count} 个来自缓存）\n")
        
        return results


class ParallelClipSelector:
    """并行视频片段选择器（使用 DeepSeek 细化）"""
    
    def __init__(self, cache_manager: CacheManager, subtitles: List[Dict], 
                 api_key: str = None, max_workers: int = 3):
        self.cache_manager = cache_manager
        self.subtitles = subtitles
        self.max_workers = max_workers
        # 从环境变量或参数获取 API key
        deepseek_key = api_key or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.clip_finder = VideoClipFinder(deepseek_key)
    
    def select_one(self, segment: Dict, index: int, audio_file: str = None) -> Dict:
        """
        为单个片段选择最佳视频片段（带缓存）
        使用 DeepSeek 在指定行号范围内细化选择
        
        Args:
            segment: 片段信息
            index: 片段索引
            audio_file: TTS音频文件路径（用于获取真实时长）
        """
        text = segment['text']
        line_start, line_end = segment['line_range']
        
        # 生成缓存键（V2不依赖固定duration）
        cache_key = f"v2:{line_start}-{line_end}:{text}"
        cache_path = self.cache_manager.get_meta_cache_path("clip_selection", cache_key)
        
        # 检查缓存
        cached_result = self.cache_manager.load_json(cache_path)
        if cached_result:
            print(f"  [{index}] ✓ 使用缓存片段选择: [{line_start}-{line_end}]")
            cached_result['index'] = index
            return cached_result
        
        # 获取真实的TTS音频时长
        import subprocess
        actual_duration = len(text) / 6.0  # 默认预估
        
        if audio_file and os.path.exists(audio_file):
            try:
                # 使用ffprobe获取音频时长
                result = subprocess.run(
                    ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                     '-of', 'default=noprint_wrappers=1:nokey=1', audio_file],
                    capture_output=True, text=True, check=True
                )
                actual_duration = float(result.stdout.strip())
                print(f"  [{index}] 🎵 真实音频时长: {actual_duration:.2f}s")
            except:
                print(f"  [{index}] ⚠️  无法获取音频时长，使用预估值: {actual_duration:.2f}s")
        
        # 调用 DeepSeek 选择片段
        print(f"  [{index}] 🤖 DeepSeek 选择片段: [{line_start}-{line_end}] {text[:40]}...")
        
        clip_info = self.clip_finder.find_best_clip(
            text, self.subtitles, line_start, line_end, actual_duration
        )
        
        if not clip_info:
            print(f"  [{index}] \033[31m✗ 无匹配\033[0m 未找到合适片段")
            return None
        
        # 显示质量评分
        quality_score = clip_info.get('quality_score', 0)
        match_level = clip_info.get('match_level', 'none')
        
        # 根据质量等级显示不同颜色
        if match_level == 'excellent':
            color = '\033[32m'  # 绿色
            icon = '✓ 优秀'
        elif match_level == 'good':
            color = '\033[36m'  # 青色
            icon = '✓ 良好'
        elif match_level == 'acceptable':
            color = '\033[33m'  # 黄色
            icon = '⚠ 可接受'
        elif match_level == 'poor':
            color = '\033[38;5;208m'  # 橙色
            icon = '⚠ 质量较差'
        else:
            color = '\033[31m'  # 红色
            icon = '✗ 无匹配'
        
        print(f"  [{index}] {color}{icon}\033[0m 质量评分: {quality_score}/100")
        
        # 添加元数据
        clip_info['index'] = index
        clip_info['text'] = text
        
        # 保存缓存
        self.cache_manager.save_json(cache_path, clip_info)
        
        return clip_info
    
    def select_all(self, segments: List[Dict]) -> List[Dict]:
        """并行选择所有视频片段"""
        print(f"\n🤖 并行选择视频片段（并发数: {self.max_workers}）...")
        
        results = [None] * len(segments)
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.select_one, seg, i): i 
                for i, seg in enumerate(segments, 1)
            }
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results[result['index'] - 1] = result
        
        # 过滤 None
        results = [r for r in results if r is not None]
        
        print(f"✅ 片段选择完成: {len(results)} 个片段\n")
        
        return results


class ParallelVideoClipper:
    """并行视频片段提取器（带缓存）"""
    
    def __init__(self, cache_manager: CacheManager, original_video: str, 
                 max_workers: int = 3):
        self.cache_manager = cache_manager
        self.original_video = original_video
        self.max_workers = max_workers
    
    def extract_one(self, clip_info: Dict, audio_file: str, index: int) -> Dict:
        """提取单个视频片段并添加配音+字幕（带缓存，支持多片段拼接）"""
        import subprocess
        import tempfile
        
        text = clip_info['text']
        
        # 检查是否为多片段模式
        is_multi_clip = clip_info.get('multi_clip', False)
        
        if is_multi_clip and 'clips' in clip_info:
            # 多片段拼接模式
            return self._extract_multi_clips(clip_info, audio_file, index)
        else:
            # 单片段模式
            start_time = clip_info['start_time']
            end_time = clip_info['end_time']
            duration = end_time - start_time
            
            return self._extract_single_clip(start_time, duration, text, audio_file, index)
    
    def _extract_multi_clips(self, clip_info: Dict, audio_file: str, index: int) -> Dict:
        """提取并拼接多个视频片段"""
        import subprocess
        import tempfile
        
        text = clip_info['text']
        clips = clip_info['clips']
        
        # 生成缓存键（基于所有片段信息）
        clips_key = ','.join([f"{c['start_time']:.2f}-{c['end_time']:.2f}" for c in clips])
        cache_key = f"multi:{clips_key}:{audio_file}:{text}"
        cache_hash = self.cache_manager.get_hash(cache_key)
        cache_path = self.cache_manager.get_clip_cache_path(cache_hash)
        
        # 检查缓存
        if cache_path.exists():
            print(f"  [{index}] ✓ 使用缓存多片段: {cache_path.name}")
            return {
                'index': index,
                'video_file': str(cache_path),
                'audio_file': audio_file,
                'text': text,
                'from_cache': True
            }
        
        print(f"       ⏳ 开始拼接 {len(clips)} 个视频片段...")
        
        # Step 1: 提取各个片段到临时文件
        temp_clips = []
        for i, clip in enumerate(clips, 1):
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.mp4', delete=False)
            temp_file.close()
            
            cmd = [
                'ffmpeg', '-y', '-loglevel', 'error',
                '-ss', str(clip['start_time']),
                '-i', self.original_video,
                '-t', str(clip['duration']),
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
                '-an',  # 不要音频，稍后统一添加
                temp_file.name
            ]
            
            print(f"       提取片段{i}/{len(clips)}: {clip['start_time']:.1f}s-{clip['end_time']:.1f}s ({clip['duration']:.1f}s)")
            subprocess.run(cmd, check=True)
            temp_clips.append(temp_file.name)
        
        # Step 2: 拼接所有片段
        concat_list = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
        for clip_file in temp_clips:
            concat_list.write(f"file '{clip_file}'\n")
        concat_list.close()
        
        temp_concat = tempfile.NamedTemporaryFile(mode='w', suffix='.mp4', delete=False)
        temp_concat.close()
        
        print(f"       拼接 {len(temp_clips)} 个片段...")
        cmd = [
            'ffmpeg', '-y', '-loglevel', 'error',
            '-f', 'concat', '-safe', '0',
            '-i', concat_list.name,
            '-c', 'copy',
            temp_concat.name
        ]
        subprocess.run(cmd, check=True)
        
        # Step 3: 添加字幕和配音
        result = self._add_subtitles_and_audio(temp_concat.name, text, audio_file, cache_path, index)
        
        # 清理临时文件
        for temp_file in temp_clips:
            try:
                os.unlink(temp_file)
            except:
                pass
        try:
            os.unlink(concat_list.name)
            os.unlink(temp_concat.name)
        except:
            pass
        
        return result
    
    def _extract_single_clip(self, start_time: float, duration: float, text: str, 
                            audio_file: str, index: int) -> Dict:
        """提取单个视频片段"""
        # 生成缓存键
        cache_key = f"{start_time:.2f}-{duration:.2f}:{audio_file}:{text}"
        cache_hash = self.cache_manager.get_hash(cache_key)
        cache_path = self.cache_manager.get_clip_cache_path(cache_hash)
        
        # 检查缓存
        if cache_path.exists():
            print(f"  [{index}] ✓ 使用缓存片段: {cache_path.name}")
            return {
                'index': index,
                'video_file': str(cache_path),
                'audio_file': audio_file,
                'text': text,
                'from_cache': True
            }
        
        print(f"       ⏳ 开始压制视频片段...")
        
        # 提取视频片段到临时文件
        import subprocess
        import tempfile
        
        temp_video = tempfile.NamedTemporaryFile(mode='w', suffix='.mp4', delete=False)
        temp_video.close()
        
        cmd = [
            'ffmpeg', '-y', '-loglevel', 'error',
            '-ss', str(start_time),
            '-i', self.original_video,
            '-t', str(duration),
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
            '-an',
            temp_video.name
        ]
        subprocess.run(cmd, check=True)
        
        # 添加字幕和配音
        result = self._add_subtitles_and_audio(temp_video.name, text, audio_file, cache_path, index)
        
        # 清理临时文件
        try:
            os.unlink(temp_video.name)
        except:
            pass
        
        return result
    
    def _add_subtitles_and_audio(self, video_file: str, text: str, audio_file: str, 
                                 output_path: Path, index: int) -> Dict:
        """为视频添加字幕和配音"""
        import subprocess
        import tempfile
        import re
        
        # 获取视频时长
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', video_file],
            capture_output=True, text=True, check=True
        )
        video_duration = float(result.stdout.strip())
        
        # 获取音频时长
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', audio_file],
            capture_output=True, text=True, check=True
        )
        audio_duration = float(result.stdout.strip())
        
        # 🚨 严格检查：视频时长必须与音频时长匹配（允许误差1秒）
        time_diff = abs(video_duration - audio_duration)
        if time_diff > 1.0:
            error_msg = f"\n{'='*80}\n❌ 致命错误：视频时长与音频时长不匹配！\n"
            error_msg += f"   视频时长: {video_duration:.2f}s\n"
            error_msg += f"   音频时长: {audio_duration:.2f}s\n"
            error_msg += f"   差距: {time_diff:.2f}s (允许最大1.0s)\n"
            error_msg += f"   文本: {text[:100]}...\n"
            error_msg += f"{'='*80}\n"
            print(error_msg)
            raise ValueError(f"视频时长 {video_duration:.2f}s 与音频时长 {audio_duration:.2f}s 差距过大 ({time_diff:.2f}s > 1.0s)")
        
        print(f"       ✓ 时长验证通过: 视频 {video_duration:.2f}s ≈ 音频 {audio_duration:.2f}s (差距 {time_diff:.2f}s)")
        
        # 使用音频时长作为基准（更准确）
        duration = audio_duration
        
        # 清理字幕文本：去掉开头的标点符号
        clean_text = text.lstrip('，。,. \t')
        
        # 创建临时字幕文件 - 按标点符号自然断句
        srt_file = tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8')
        
        # 按标点符号分割字幕（逗号、句号、感叹号、问号）
        segments = re.split(r'([，。,!！?？])', clean_text)
        
        # 重组：将标点符号附加到前一个片段
        merged_segments = []
        for i in range(0, len(segments), 2):
            if i < len(segments):
                seg = segments[i]
                if i + 1 < len(segments):
                    seg += segments[i + 1]  # 附加标点
                if seg.strip():  # 跳过空片段
                    merged_segments.append(seg)
        
        if not merged_segments:  # 如果没有标点，整段作为一个字幕
            merged_segments = [clean_text]
        
        # 计算每段的时间（按字数比例分配）
        total_chars = sum(len(s) for s in merged_segments)
        
        # 生成 SRT 内容
        srt_content = []
        current_time = 0.0
        for idx, seg in enumerate(merged_segments):
            seg_duration = (len(seg) / total_chars) * duration
            start = current_time
            end = current_time + seg_duration
            srt_content.append(f"{idx+1}\n{self._format_srt_time(start)} --> {self._format_srt_time(end)}\n{seg}\n")
            current_time = end
        
        srt_file.write('\n'.join(srt_content))
        srt_file.close()
        
        print(f"       字幕文件: {srt_file.name}")
        print(f"       字幕分段: {len(merged_segments)} 段（按标点符号自然断句）")
        print(f"       字幕内容: {clean_text[:50]}...")
        
        # FFmpeg 命令：添加配音 + 烧录字幕 + 缩放
        cmd = [
            'ffmpeg', '-y', '-loglevel', 'error',
            '-i', video_file,
            '-i', audio_file,
            '-filter_complex',
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,subtitles={srt_file.name}:force_style='Fontsize=8,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=1,MarginV=40,Alignment=2'[vout]",
            '-map', '[vout]',
            '-map', '1:a',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ar', '44100',
            '-ac', '2',
            str(output_path)
        ]
        
        try:
            print(f"       🎬 FFmpeg 添加字幕和配音...")
            subprocess.run(cmd, check=True, timeout=120)
            print(f"       ✅ 压制成功: {output_path.name}")
        except Exception as e:
            print(f"       ❌ 压制失败: {e}")
            return None
        finally:
            try:
                os.unlink(srt_file.name)
            except:
                pass
        
        return {
            'index': index,
            'video_file': str(output_path),
            'audio_file': audio_file,
            'text': text,
            'from_cache': False
        }
    
    def extract_all(self, clip_selections: List[Dict], tts_results: List[Dict]) -> List[Dict]:
        """顺序提取所有视频片段（逐个对齐和压制）"""
        print(f"\n✂️  顺序提取视频片段（逐个处理）...")
        print("=" * 80)
        
        results = []
        
        # 按顺序处理每个片段
        for clip_info in clip_selections:
            index = clip_info['index']
            
            # 找到对应的 TTS 结果
            tts_result = next((t for t in tts_results if t['index'] == index), None)
            if not tts_result:
                print(f"  [{index}] ⚠️  跳过: 未找到对应的 TTS 音频")
                continue
            
            audio_file = tts_result['audio_file']
            
            # 处理单个片段
            print(f"\n  [{index}] 📝 开始对齐字幕...")
            print(f"       文本: {clip_info['text'][:60]}...")
            print(f"       时间: {clip_info['start_time']:.1f}s - {clip_info['end_time']:.1f}s")
            print(f"       音频: {audio_file}")
            
            result = self.extract_one(clip_info, audio_file, index)
            
            if result:
                results.append(result)
                print(f"  [{index}] ✅ 压制完成!")
                print(f"       输出路径: {result['video_file']}")
                print(f"       文件大小: {os.path.getsize(result['video_file']) / (1024*1024):.2f} MB")
            else:
                print(f"  [{index}] ❌ 处理失败")
            
            print("-" * 80)
        
        cache_count = sum(1 for r in results if r.get('from_cache'))
        print(f"\n✅ 视频片段提取完成: {len(results)} 个片段（{cache_count} 个来自缓存）\n")
        
        return results
    
    def _format_srt_time(self, seconds: float) -> str:
        """格式化 SRT 时间"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


class VideoComposer:
    """视频合成器"""
    
    @staticmethod
    def compose(clips: List[Dict], output_file: str):
        """合成最终视频"""
        import subprocess
        
        print(f"\n🎬 合成最终视频...")
        
        # 创建合并列表
        temp_dir = os.path.dirname(output_file) or '.'
        concat_file = os.path.join(temp_dir, 'concat_list.txt')
        
        with open(concat_file, 'w', encoding='utf-8') as f:
            for clip in clips:
                f.write(f"file '{clip['video_file']}'\n")
        
        # 合并（重新编码音频确保兼容性）
        cmd = [
            'ffmpeg', '-y', '-loglevel', 'warning',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_file,
            '-c:v', 'copy',  # 视频直接复制
            '-c:a', 'aac',  # 音频重新编码为AAC
            '-b:a', '192k',  # 提高音频比特率
            '-ar', '44100',  # 采样率44.1kHz
            '-ac', '2',  # 立体声
            output_file
        ]
        
        try:
            subprocess.run(cmd, check=True)
            print(f"✅ 最终视频已保存: {output_file}\n")
        except subprocess.CalledProcessError as e:
            print(f"❌ 合成失败: {e}\n")
        finally:
            if os.path.exists(concat_file):
                os.remove(concat_file)


def main():
    parser = argparse.ArgumentParser(
        description='完整视频生成流程 V2：支持连续文案+嵌入行号标记'
    )
    
    parser.add_argument('script_file', help='V2文案脚本文件（格式: 文本[行号]文本[行号]...）')
    parser.add_argument('srt_file', help='原始字幕文件（SRT 格式）')
    parser.add_argument('video_file', help='原始视频文件')
    parser.add_argument('-o', '--output', default='final_output_v2.mp4', help='输出视频文件')
    
    parser.add_argument('--chunk-words', type=int, default=30, 
                       help='每个片段的字数（默认30字，约6-8秒TTS）')
    parser.add_argument('--speaker', default='龙白芷', help='TTS 语音角色（默认: 龙白芷）')
    parser.add_argument('--tts-workers', type=int, default=4, help='TTS 并发数（默认: 4）')
    parser.add_argument('--clip-workers', type=int, default=3, help='片段选择并发数（默认: 3）')
    parser.add_argument('--video-workers', type=int, default=3, help='视频提取并发数（默认: 3）')
    
    parser.add_argument('--cache-dir', default='.cache', help='缓存目录（默认: .cache）')
    parser.add_argument('--force-clean', action='store_true', help='清理缓存后重新生成')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("完整视频生成流程 V2 (连续文案+嵌入行号)")
    print("=" * 80)
    print(f"文案脚本: {args.script_file}")
    print(f"原始字幕: {args.srt_file}")
    print(f"原始视频: {args.video_file}")
    print(f"输出文件: {args.output}")
    print(f"片段字数: {args.chunk_words} 字/片段")
    print(f"TTS 并发数: {args.tts_workers}")
    print(f"片段选择并发数: {args.clip_workers}")
    print(f"视频提取并发数: {args.video_workers}")
    print(f"缓存目录: {args.cache_dir}")
    print("=" * 80)
    
    # 初始化缓存管理器
    cache_manager = CacheManager(args.cache_dir)
    if args.force_clean:
        print("\n🗑️  清理缓存...")
        cache_manager.clear()
        print("✅ 缓存已清理\n")
    
    # Step 1: 解析 V2 格式文案脚本
    print("\n📄 Step 1: 解析 V2 格式文案脚本...")
    segments = ScriptParserV2.parse_script_file(args.script_file, args.chunk_words)
    print(f"✅ 共解析 {len(segments)} 个片段\n")
    
    # 显示前3个片段预览
    print("预览前3个片段:")
    for i, seg in enumerate(segments[:3], 1):
        print(f"  [{i}] {seg['text'][:50]}... (行号: {seg['line_range']})")
    if len(segments) > 3:
        print(f"  ... 还有 {len(segments) - 3} 个片段")
    print()
    
    # Step 2: 解析原始字幕
    print("📄 Step 2: 解析原始字幕...")
    subtitles = SRTParser.parse_srt(args.srt_file)
    print(f"✅ 共解析 {len(subtitles)} 条字幕\n")
    
    # 检查必需的 API keys（使用环境变量或配置文件中的默认值）
    deepseek_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or "sk-b806e7ca03ab4a9cb12445a659349268"
    bailian_key = os.getenv("BAILIAN_API_KEY") or "sk-f0b5e3f543d64b0d8640888cb4327b74"
    
    # Step 3: 流水线处理 - TTS + 片段选择 + 视频压制
    print("\n🔄 流水线处理: TTS → 片段选择 → 视频压制")
    print("=" * 80)
    
    # 初始化处理器
    tts_generator = ParallelTTSGenerator(
        cache_manager, args.speaker, api_key=bailian_key, max_workers=1  # 单线程顺序处理
    )
    clip_selector = ParallelClipSelector(
        cache_manager, subtitles, api_key=deepseek_key, max_workers=1
    )
    video_clipper = ParallelVideoClipper(
        cache_manager, args.video_file, max_workers=1
    )
    
    video_clips = []
    
    # 逐个处理每个段落
    for i, segment in enumerate(segments, 1):
        print(f"\n{'='*80}")
        print(f"处理第 {i}/{len(segments)} 个片段")
        print(f"{'='*80}")
        
        # Step 3.1: 生成 TTS
        print(f"  🎤 [{i}] 生成 TTS: {segment['text'][:50]}...")
        tts_result = tts_generator.generate_one(segment, i)
        if not tts_result:
            print(f"  ❌ [{i}] TTS 生成失败，跳过")
            continue
        
        print(f"  ✅ [{i}] TTS 完成: {tts_result['audio_file']}")
        
        # Step 3.2: 选择视频片段（传入真实音频文件）
        print(f"  🤖 [{i}] DeepSeek 选择片段...")
        clip_selection = clip_selector.select_one(tts_result, i, audio_file=tts_result['audio_file'])
        if not clip_selection:
            print(f"  ❌ [{i}] 片段选择失败，跳过")
            continue
        
        print(f"  ✅ [{i}] 片段选择完成: [{clip_selection['start_time']:.1f}s - {clip_selection['end_time']:.1f}s]")
        
        # Step 3.3: 立即压制视频
        print(f"  📝 [{i}] 开始对齐字幕并压制视频...")
        print(f"       文本: {clip_selection['text'][:60]}...")
        print(f"       时间: {clip_selection['start_time']:.1f}s - {clip_selection['end_time']:.1f}s")
        print(f"       音频: {tts_result['audio_file']}")
        
        video_clip = video_clipper.extract_one(clip_selection, tts_result['audio_file'], i)
        if video_clip:
            video_clips.append(video_clip)
            print(f"  ✅ [{i}] 压制完成!")
            print(f"       输出路径: {video_clip['video_file']}")
            print(f"       文件大小: {os.path.getsize(video_clip['video_file']) / (1024*1024):.2f} MB")
        else:
            print(f"  ❌ [{i}] 视频压制失败")
    
    print(f"\n{'='*80}")
    print(f"✅ 所有片段处理完成: {len(video_clips)}/{len(segments)} 个成功")
    print(f"{'='*80}\n")
    
    # Step 4: 合成最终视频
    if video_clips:
        VideoComposer.compose(video_clips, args.output)
    else:
        print("❌ 没有成功生成任何视频片段，无法合成最终视频")
    
    print("=" * 80)
    print("✅ 全部完成！")
    print("=" * 80)


if __name__ == "__main__":
    import sys
    sys.exit(main())
