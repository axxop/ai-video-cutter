#!/usr/bin/env python3
"""
完整视频生成流程：
1. 解析文案脚本（带行号范围）
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


class ScriptParser:
    """文案脚本解析器"""
    
    @staticmethod
    def parse_script_file(script_file: str) -> List[Dict]:
        """
        解析文案脚本文件
        格式: [时间] [行号] 内容
        
        Returns:
            [{'duration': 15, 'line_range': [1, 50], 'text': '...'}]
        """
        segments = []
        
        with open(script_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                # 解析格式: [15s] [1-50] 内容...
                match = re.match(r'\[(\d+)s\]\s*\[(\d+)-(\d+)\]\s*(.+)', line)
                if match:
                    duration = int(match.group(1))
                    line_start = int(match.group(2))
                    line_end = int(match.group(3))
                    text = match.group(4)
                    
                    segments.append({
                        'duration': duration,
                        'line_range': [line_start, line_end],
                        'text': text
                    })
                else:
                    print(f"⚠️  无法解析行: {line[:60]}...")
        
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
        duration = segment['duration']
        
        # 检查缓存
        cache_path = self.cache_manager.get_tts_cache_path(text, self.speaker_id)
        
        if cache_path.exists():
            print(f"  [{index}] ✓ 使用缓存 TTS: {cache_path.name}")
            return {
                'index': index,
                'audio_file': str(cache_path),
                'text': text,
                'duration': duration,
                'line_range': segment['line_range'],
                'from_cache': True
            }
        
        # 生成 TTS
        try:
            print(f"  [{index}] 🎤 生成 TTS: {text[:40]}...")
            result = self.tts_client.synthesize(text, str(cache_path))
            
            return {
                'index': index,
                'audio_file': str(cache_path),
                'text': text,
                'duration': duration,
                'line_range': segment['line_range'],
                'from_cache': False
            }
        except Exception as e:
            print(f"  [{index}] ❌ TTS 生成失败: {e}")
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
    
    def select_one(self, segment: Dict, index: int) -> Dict:
        """
        为单个片段选择最佳视频片段（带缓存）
        使用 DeepSeek 在指定行号范围内细化选择
        """
        text = segment['text']
        audio_duration = segment['duration']
        line_start, line_end = segment['line_range']
        
        # 生成缓存键
        cache_key = f"{line_start}-{line_end}:{text}:{audio_duration}"
        cache_path = self.cache_manager.get_meta_cache_path("clip_selection", cache_key)
        
        # 检查缓存
        cached_result = self.cache_manager.load_json(cache_path)
        if cached_result:
            print(f"  [{index}] ✓ 使用缓存片段选择: [{line_start}-{line_end}]")
            cached_result['index'] = index
            return cached_result
        
        # 调用 DeepSeek 选择片段
        print(f"  [{index}] 🤖 DeepSeek 选择片段: [{line_start}-{line_end}] {text[:40]}...")
        
        clip_info = self.clip_finder.find_best_clip(
            text, self.subtitles, line_start, line_end, audio_duration
        )
        
        if not clip_info:
            print(f"  [{index}] ⚠️  未找到合适片段")
            return None
        
        # 添加元数据
        clip_info['index'] = index
        clip_info['text'] = text
        clip_info['audio_duration'] = audio_duration
        
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
        """提取单个视频片段并添加配音+字幕（带缓存）"""
        import subprocess
        import tempfile
        
        start_time = clip_info['start_time']
        end_time = clip_info['end_time']
        text = clip_info['text']
        audio_duration = clip_info['audio_duration']
        
        # 视频时长 = 音频时长 + 2 秒
        video_duration = audio_duration + 2.0
        
        # 调整结束时间
        if (end_time - start_time) > video_duration:
            end_time = start_time + video_duration
        
        # 生成缓存键
        cache_key = f"{start_time:.2f}-{end_time:.2f}:{audio_file}:{text}"
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
        
        # 提取视频片段
        print(f"  [{index}] ✂️  提取片段: {start_time:.1f}s-{end_time:.1f}s + 配音")
        
        duration = end_time - start_time
        
        # 创建临时字幕文件
        srt_file = tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8')
        srt_file.write(f"1\n00:00:00,000 --> {self._format_srt_time(duration)}\n{text}\n")
        srt_file.close()
        
        # FFmpeg 命令：提取视频 + 添加配音 + 烧录字幕
        cmd = [
            'ffmpeg', '-y', '-loglevel', 'error',
            '-ss', str(start_time),
            '-i', self.original_video,
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
            str(cache_path)
        ]
        
        try:
            subprocess.run(cmd, check=True, timeout=120)
            print(f"  [{index}] ✅ 片段已保存: {cache_path.name}")
        except Exception as e:
            print(f"  [{index}] ❌ 提取失败: {e}")
            return None
        finally:
            try:
                os.unlink(srt_file.name)
            except:
                pass
        
        return {
            'index': index,
            'video_file': str(cache_path),
            'audio_file': audio_file,
            'text': text,
            'from_cache': False
        }
    
    def extract_all(self, clip_selections: List[Dict], tts_results: List[Dict]) -> List[Dict]:
        """并行提取所有视频片段"""
        print(f"\n✂️  并行提取视频片段（并发数: {self.max_workers}）...")
        
        # 匹配 clip_selections 和 tts_results
        tasks = []
        for clip_info in clip_selections:
            index = clip_info['index']
            # 找到对应的 TTS 结果
            tts_result = next((t for t in tts_results if t['index'] == index), None)
            if tts_result:
                tasks.append((clip_info, tts_result['audio_file'], index))
        
        results = [None] * len(tasks)
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.extract_one, clip_info, audio_file, idx): idx - 1
                for clip_info, audio_file, idx in tasks
            }
            
            for future in as_completed(futures):
                result_index = futures[future]
                result = future.result()
                if result:
                    results[result_index] = result
        
        # 过滤 None
        results = [r for r in results if r is not None]
        
        cache_count = sum(1 for r in results if r.get('from_cache'))
        print(f"✅ 视频片段提取完成: {len(results)} 个片段（{cache_count} 个来自缓存）\n")
        
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
        
        # 合并
        cmd = [
            'ffmpeg', '-y', '-loglevel', 'warning',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_file,
            '-c', 'copy',
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
        description='完整视频生成流程：文案 → TTS → 片段选择 → 视频合成'
    )
    
    parser.add_argument('script_file', help='文案脚本文件（格式: [时间] [行号] 内容）')
    parser.add_argument('srt_file', help='原始字幕文件（SRT 格式）')
    parser.add_argument('video_file', help='原始视频文件')
    parser.add_argument('-o', '--output', default='final_output.mp4', help='输出视频文件')
    
    parser.add_argument('--speaker', default='龙白芷', help='TTS 语音角色（默认: 龙白芷）')
    parser.add_argument('--tts-workers', type=int, default=4, help='TTS 并发数（默认: 4）')
    parser.add_argument('--clip-workers', type=int, default=3, help='片段选择并发数（默认: 3）')
    parser.add_argument('--video-workers', type=int, default=3, help='视频提取并发数（默认: 3）')
    
    parser.add_argument('--cache-dir', default='.cache', help='缓存目录（默认: .cache）')
    parser.add_argument('--force-clean', action='store_true', help='清理缓存后重新生成')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("完整视频生成流程")
    print("=" * 80)
    print(f"文案脚本: {args.script_file}")
    print(f"原始字幕: {args.srt_file}")
    print(f"原始视频: {args.video_file}")
    print(f"输出文件: {args.output}")
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
    
    # Step 1: 解析文案脚本
    print("\n📄 Step 1: 解析文案脚本...")
    segments = ScriptParser.parse_script_file(args.script_file)
    print(f"✅ 共解析 {len(segments)} 个段落\n")
    
    # Step 2: 解析原始字幕
    print("📄 Step 2: 解析原始字幕...")
    subtitles = SRTParser.parse_srt(args.srt_file)
    print(f"✅ 共解析 {len(subtitles)} 条字幕\n")
    
    # 检查必需的 API keys
    deepseek_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not deepseek_key:
        print("\n❌ 错误: 未找到 DEEPSEEK_API_KEY 或 OPENAI_API_KEY 环境变量")
        print("   请设置环境变量: export DEEPSEEK_API_KEY=your_api_key")
        return 1
    
    bailian_key = os.getenv("BAILIAN_API_KEY")
    if not bailian_key:
        print("\n❌ 错误: 未找到 BAILIAN_API_KEY 环境变量")
        print("   请设置环境变量: export BAILIAN_API_KEY=your_api_key")
        return 1
    
    # Step 3: 并行生成 TTS 音频
    tts_generator = ParallelTTSGenerator(
        cache_manager, args.speaker, max_workers=args.tts_workers
    )
    tts_results = tts_generator.generate_all(segments)
    
    # Step 4: 并行选择视频片段
    clip_selector = ParallelClipSelector(
        cache_manager, subtitles, max_workers=args.clip_workers
    )
    clip_selections = clip_selector.select_all(tts_results)
    
    # Step 5: 并行提取视频片段
    video_clipper = ParallelVideoClipper(
        cache_manager, args.video_file, max_workers=args.video_workers
    )
    video_clips = video_clipper.extract_all(clip_selections, tts_results)
    
    # Step 6: 合成最终视频
    VideoComposer.compose(video_clips, args.output)
    
    print("=" * 80)
    print("✅ 全部完成！")
    print("=" * 80)


if __name__ == "__main__":
    import sys
    sys.exit(main())
