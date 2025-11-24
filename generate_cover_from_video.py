#!/usr/bin/env python3
"""
从视频中提取关键帧，使用百炼万相添加文字生成封面
1. 从视频高潮部分提取关键帧
2. 使用图生图 API 添加标题文字
"""

import os
import argparse
import subprocess
import requests
import time
import base64
from pathlib import Path
from typing import Optional, List
import json
from PIL import Image, ImageDraw, ImageFont


class VideoFrameExtractor:
    """视频关键帧提取器"""
    
    @staticmethod
    def extract_frame(video_path: str, timestamp: float, output_path: str, vertical: bool = True) -> bool:
        """
        从视频中提取指定时间点的帧
        
        Args:
            video_path: 视频文件路径
            timestamp: 时间点（秒）
            output_path: 输出图片路径
            vertical: 是否输出竖版（9:16），默认 True
            
        Returns:
            是否提取成功
        """
        try:
            print(f"📸 从视频提取关键帧...")
            print(f"   视频: {video_path}")
            print(f"   时间点: {timestamp:.2f}s")
            if vertical:
                print(f"   尺寸: 竖版 1080x1920 (9:16)")
            
            # 使用 ffmpeg 提取帧并裁剪为竖版
            if vertical:
                # 竖版：先缩放高度到1920，然后裁剪中心宽度到1080
                # scale=-1:1920 保持宽高比缩放高度到1920
                # crop=1080:1920 从中心裁剪1080x1920
                cmd = [
                    'ffmpeg',
                    '-ss', str(timestamp),
                    '-i', video_path,
                    '-vf', 'scale=-1:1920,crop=1080:1920',  # 先缩放高度，再裁剪中心
                    '-vframes', '1',
                    '-q:v', '2',  # 高质量
                    '-y',  # 覆盖已存在的文件
                    output_path
                ]
            else:
                # 横版：保持原样
                cmd = [
                    'ffmpeg',
                    '-ss', str(timestamp),
                    '-i', video_path,
                    '-vframes', '1',
                    '-q:v', '2',  # 高质量
                    '-y',  # 覆盖已存在的文件
                    output_path
                ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode == 0 and os.path.exists(output_path):
                print(f"✅ 关键帧已保存: {output_path}")
                return True
            else:
                print(f"❌ 提取失败: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ 提取关键帧时出错: {e}")
            return False
    
    @staticmethod
    def get_video_duration(video_path: str) -> Optional[float]:
        """
        获取视频时长
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            视频时长（秒），失败返回None
        """
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode == 0:
                duration = float(result.stdout.strip())
                return duration
            else:
                return None
                
        except Exception as e:
            print(f"⚠️  获取视频时长失败: {e}")
            return None
    
    @staticmethod
    def find_climax_timestamp(video_path: str, clips_info_path: str = None) -> float:
        """
        找到视频高潮部分的时间点
        
        Args:
            video_path: 视频文件路径
            clips_info_path: clips_info.json 路径（可选）
            
        Returns:
            时间戳（秒）
        """
        # 如果有 clips_info.json，从中找到中间偏后的片段
        if clips_info_path and os.path.exists(clips_info_path):
            try:
                with open(clips_info_path, 'r', encoding='utf-8') as f:
                    clips_info = json.load(f)
                
                if clips_info and len(clips_info) > 0:
                    # 取中间偏后的片段（70%位置）
                    index = int(len(clips_info) * 0.7)
                    clip = clips_info[index]
                    
                    # 取该片段的中间时间点
                    start = clip.get('original_start', 0)
                    end = clip.get('original_end', start + 5)
                    timestamp = (start + end) / 2
                    
                    print(f"✓ 从 clips_info 找到高潮片段: {timestamp:.2f}s")
                    return timestamp
                    
            except Exception as e:
                print(f"⚠️  解析 clips_info 失败: {e}")
        
        # 否则取视频 60% 位置作为高潮
        duration = VideoFrameExtractor.get_video_duration(video_path)
        if duration:
            timestamp = duration * 0.6
            print(f"✓ 使用视频 60% 位置作为高潮: {timestamp:.2f}s")
            return timestamp
        else:
            # 默认 30 秒
            print(f"⚠️  使用默认时间点: 30s")
            return 30.0


class CoverGenerator:
    """封面生成器 - 在图片上添加文字"""
    
    @staticmethod
    def add_text_to_image(
        image_path: str,
        title: str,
        output_path: str,
        subtitle: str = None
    ) -> bool:
        """
        在图片上添加文字
        
        Args:
            image_path: 输入图片路径
            title: 主标题
            output_path: 输出图片路径
            subtitle: 副标题（可选）
            
        Returns:
            是否生成成功
        """
        try:
            print(f"🎨 正在添加文字到封面...")
            print(f"   标题: {title}")
            if subtitle:
                print(f"   副标题: {subtitle}")
            
            # 打开图片
            img = Image.open(image_path)
            draw = ImageDraw.Draw(img)
            
            # 图片尺寸
            width, height = img.size
            
            # 尝试加载字体（如果没有就用默认）
            try:
                # 尝试几个常见的中文字体路径
                font_paths = [
                    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
                    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
                    "/usr/share/fonts/noto-cjk/NotoSansCJK-Light.ttc",
                    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                    "/System/Library/Fonts/PingFang.ttc",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                ]
                
                title_font = None
                subtitle_font = None
                for font_path in font_paths:
                    if os.path.exists(font_path):
                        print(f"   ✓ 使用字体: {font_path}")
                        title_font = ImageFont.truetype(font_path, int(height * 0.08))
                        subtitle_font = ImageFont.truetype(font_path, int(height * 0.05))
                        break
                
                if not title_font:
                    print(f"   ⚠️  未找到中文字体，使用默认字体")
                    title_font = ImageFont.load_default()
                    subtitle_font = ImageFont.load_default()
                    
            except Exception as e:
                print(f"   ⚠️  加载字体失败，使用默认字体: {e}")
                title_font = ImageFont.load_default()
                subtitle_font = ImageFont.load_default()
            
            # 添加半透明背景遮罩（底部）
            overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            
            # 渐变黑色遮罩（底部 30%）
            mask_height = int(height * 0.35)
            for i in range(mask_height):
                alpha = int(180 * (i / mask_height))
                overlay_draw.rectangle(
                    [(0, height - mask_height + i), (width, height - mask_height + i + 1)],
                    fill=(0, 0, 0, alpha)
                )
            
            img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
            draw = ImageDraw.Draw(img)
            
            # 计算标题位置（底部居中）
            # 使用 textbbox 获取文本边界框
            title_bbox = draw.textbbox((0, 0), title, font=title_font)
            title_width = title_bbox[2] - title_bbox[0]
            title_height = title_bbox[3] - title_bbox[1]
            
            title_x = (width - title_width) // 2
            title_y = height - int(height * 0.20)
            
            # 绘制标题阴影
            shadow_offset = 3
            draw.text((title_x + shadow_offset, title_y + shadow_offset), title, 
                     font=title_font, fill=(0, 0, 0, 255))
            
            # 绘制标题
            draw.text((title_x, title_y), title, font=title_font, fill=(255, 255, 255, 255))
            
            # 如果有副标题
            if subtitle:
                subtitle_bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
                subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
                subtitle_x = (width - subtitle_width) // 2
                subtitle_y = title_y + title_height + int(height * 0.03)
                
                # 副标题阴影
                draw.text((subtitle_x + 2, subtitle_y + 2), subtitle, 
                         font=subtitle_font, fill=(0, 0, 0, 255))
                # 副标题文字
                draw.text((subtitle_x, subtitle_y), subtitle, 
                         font=subtitle_font, fill=(255, 200, 100, 255))
            
            # 保存
            output_dir = os.path.dirname(output_path)
            if output_dir:
                Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            img.save(output_path, quality=95)
            
            print(f"✅ 封面已保存: {output_path}")
            return True
            
        except Exception as e:
            print(f"❌ 添加文字失败: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    parser = argparse.ArgumentParser(
        description="从视频提取关键帧并生成带文字的封面"
    )
    
    parser.add_argument(
        "video",
        help="视频文件路径"
    )
    
    parser.add_argument(
        "-t", "--title",
        required=True,
        help="封面主标题"
    )
    
    parser.add_argument(
        "-s", "--subtitle",
        help="封面副标题（可选）"
    )
    
    parser.add_argument(
        "-o", "--output",
        default="cover.png",
        help="输出封面路径（默认: cover.png）"
    )
    
    parser.add_argument(
        "--timestamp",
        type=float,
        help="指定提取帧的时间点（秒），不指定则自动寻找高潮部分"
    )
    
    parser.add_argument(
        "--clips-info",
        help="clips_info.json 路径，用于智能定位高潮片段"
    )
    
    parser.add_argument(
        "--frame-only",
        action="store_true",
        help="仅提取关键帧，不添加文字"
    )
    
    args = parser.parse_args()
    
    # 检查视频文件
    if not os.path.exists(args.video):
        print(f"❌ 错误: 视频文件不存在 → {args.video}")
        return 1
    
    print("=" * 80)
    print("视频封面生成器（从视频提取关键帧）")
    print("=" * 80)
    print(f"视频文件: {args.video}")
    print(f"主标题: {args.title}")
    if args.subtitle:
        print(f"副标题: {args.subtitle}")
    print(f"输出: {args.output}")
    print("=" * 80)
    
    # 步骤 1: 提取关键帧
    extractor = VideoFrameExtractor()
    
    # 确定时间点
    if args.timestamp is not None:
        timestamp = args.timestamp
    else:
        timestamp = extractor.find_climax_timestamp(args.video, args.clips_info)
    
    # 临时帧文件
    temp_frame = "/tmp/video_frame_temp.png"
    
    # 提取竖版帧
    success = extractor.extract_frame(args.video, timestamp, temp_frame, vertical=True)
    if not success:
        print("❌ 提取关键帧失败")
        return 1
    
    # 如果只需要帧，直接保存并退出
    if args.frame_only:
        import shutil
        shutil.move(temp_frame, args.output)
        print(f"✅ 关键帧已保存: {args.output}")
        return 0
    
    # 步骤 2: 添加文字
    generator = CoverGenerator()
    
    success = generator.add_text_to_image(
        image_path=temp_frame,
        title=args.title,
        output_path=args.output,
        subtitle=args.subtitle
    )
    
    # 清理临时文件
    if os.path.exists(temp_frame):
        os.remove(temp_frame)
    
    if success:
        print("\n✅ 封面生成完成！")
        return 0
    else:
        print("\n❌ 封面生成失败")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
