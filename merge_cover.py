#!/usr/bin/env python3
"""
将封面图片添加到视频文件中 (设置 metadata cover)
"""

import os
import argparse
import subprocess
import sys

def add_cover(video_path, cover_path, output_path):
    """
    使用 ffmpeg 将封面添加到视频
    """
    if not os.path.exists(video_path):
        print(f"❌ 视频文件不存在: {video_path}")
        return False
    
    if not os.path.exists(cover_path):
        print(f"❌ 封面文件不存在: {cover_path}")
        return False
        
    print(f"🎬 正在处理视频: {video_path}")
    print(f"🖼️  添加封面: {cover_path}")
    print(f"💾 输出文件: {output_path}")
    
    # 检测视频容器格式
    ext = os.path.splitext(output_path)[1].lower()
    
    cmd = []
    if ext == '.mp4':
        # MP4 格式添加封面
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-i', cover_path,
            '-map', '0',
            '-map', '1',
            '-c', 'copy',
            '-c:v:1', 'png',
            '-disposition:v:1', 'attached_pic',
            '-y',
            output_path
        ]
    elif ext == '.mkv':
        # MKV 格式添加封面 (作为附件)
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-attach', cover_path,
            '-metadata:s:t', 'mimetype=image/png',
            '-c', 'copy',
            '-y',
            output_path
        ]
    else:
        # 其他格式尝试通用方法
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-i', cover_path,
            '-map', '0',
            '-map', '1',
            '-c', 'copy',
            '-disposition:v:1', 'attached_pic',
            '-y',
            output_path
        ]
        
    try:
        # 运行 ffmpeg
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # 实时读取输出（可选）
        stdout, stderr = process.communicate()
        
        if process.returncode == 0:
            print(f"\n✅ 成功！封面已添加到: {output_path}")
            return True
        else:
            print(f"\n❌ 失败: ffmpeg 返回错误")
            print(stderr)
            return False
            
    except Exception as e:
        print(f"\n❌ 执行出错: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="给视频添加封面")
    parser.add_argument("video", help="输入视频文件路径")
    parser.add_argument("cover", help="封面图片路径")
    parser.add_argument("-o", "--output", help="输出视频路径 (默认: output_with_cover.mp4/mkv)")
    
    args = parser.parse_args()
    
    output = args.output
    if not output:
        base, ext = os.path.splitext(args.video)
        output = f"{base}_with_cover{ext}"
        
    add_cover(args.video, args.cover, output)

if __name__ == "__main__":
    main()
