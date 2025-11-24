#!/usr/bin/env python3
"""
视频片段对齐测试 Demo
测试单个片段的提取、配音和字幕对齐
"""

import os
import subprocess
import tempfile

# 配置
VIDEO_FILE = "origin_videos/Detective.Conan.The.Million.dollar.Pentagram.2024.V2.1080p.BluRay.x265.10bit.DTS.3Audio-ADE.mkv"
AUDIO_FILE = ".cache/tts/5febff596c9ba0716866b6fede18ffb9.wav"  # 第一个片段的音频
OUTPUT_FILE = "demo_output.mp4"

# 片段信息
START_TIME = 94.05  # 开始时间（秒）
END_TIME = 106.61   # 结束时间（秒）
SUBTITLE_TEXT = "怪盗基德发出预告信要偷两把肋差刀！斧江财团戒备森严，但基德克星柯南和服部平次已经赶到现场。"

print("=" * 80)
print("视频片段对齐测试 Demo")
print("=" * 80)
print(f"原始视频: {VIDEO_FILE}")
print(f"配音音频: {AUDIO_FILE}")
print(f"片段时间: {START_TIME}s - {END_TIME}s (时长: {END_TIME - START_TIME:.2f}s)")
print(f"字幕文本: {SUBTITLE_TEXT}")
print("=" * 80)

# 计算时长
video_duration = END_TIME - START_TIME
audio_duration = video_duration + 2.0  # 音频时长 = 视频时长 + 2秒

print(f"\n1. 计算时长:")
print(f"   视频片段时长: {video_duration:.2f}s")
print(f"   音频时长(+2s): {audio_duration:.2f}s")

# 创建临时字幕文件
def format_srt_time(seconds):
    """格式化 SRT 时间"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

srt_file = tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8')
srt_content = f"1\n00:00:00,000 --> {format_srt_time(video_duration)}\n{SUBTITLE_TEXT}\n"
srt_file.write(srt_content)
srt_file.close()

print(f"\n2. 创建字幕文件:")
print(f"   路径: {srt_file.name}")
print(f"   内容:")
print(f"   {srt_content}")

# 构建 FFmpeg 命令
print(f"\n3. FFmpeg 命令构建:")
print(f"   提取视频: {START_TIME}s 开始, 时长 {video_duration:.2f}s")
print(f"   添加配音: {AUDIO_FILE}")
print(f"   烧录字幕: {srt_file.name}")
print(f"   缩放到竖屏: 1080x1920")

cmd = [
    'ffmpeg', '-y', '-loglevel', 'info',  # 使用 info 级别查看详细信息
    # 输入
    '-ss', str(START_TIME),
    '-i', VIDEO_FILE,
    '-i', AUDIO_FILE,
    '-t', str(video_duration),
    # 视频处理: 缩放 + 字幕
    '-filter_complex',
    f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
    f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
    f"subtitles={srt_file.name}:force_style='Fontsize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=1,MarginV=80,Alignment=2'[vout]",
    # 映射输出
    '-map', '[vout]',  # 处理后的视频
    '-map', '1:a',     # 音频流
    # 编码参数
    '-c:v', 'libx264',
    '-preset', 'ultrafast',
    '-crf', '23',
    '-c:a', 'aac',
    '-b:a', '128k',
    OUTPUT_FILE
]

print(f"\n4. 执行 FFmpeg:")
print(f"   命令: {' '.join(cmd[:10])}...")
print(f"\n开始提取...\n")

try:
    result = subprocess.run(cmd, check=True, capture_output=False, text=True)
    print(f"\n✅ 成功! 输出文件: {OUTPUT_FILE}")
    
    # 获取文件信息
    if os.path.exists(OUTPUT_FILE):
        file_size = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
        print(f"   文件大小: {file_size:.2f} MB")
        
        # 使用 ffprobe 获取视频信息
        probe_cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            OUTPUT_FILE
        ]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
        if probe_result.returncode == 0:
            actual_duration = float(probe_result.stdout.strip())
            print(f"   实际时长: {actual_duration:.2f}s")
            print(f"   预期时长: {video_duration:.2f}s")
            print(f"   差异: {abs(actual_duration - video_duration):.2f}s")

except subprocess.CalledProcessError as e:
    print(f"\n❌ 失败: {e}")
except Exception as e:
    print(f"\n❌ 错误: {e}")
finally:
    # 清理临时文件
    try:
        os.unlink(srt_file.name)
        print(f"\n5. 清理临时文件: {srt_file.name}")
    except:
        pass

print("\n" + "=" * 80)
print("测试完成!")
print("=" * 80)
print(f"\n请检查输出文件: {OUTPUT_FILE}")
print("查看字幕是否正确对齐、配音是否同步")
