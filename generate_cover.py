#!/usr/bin/env python3
"""
使用百炼 API (通义万相) 生成视频封面
支持根据视频内容、主题自动生成吸引人的封面图
"""

import os
import argparse
import requests
from pathlib import Path
from typing import Optional
import time


class CoverGenerator:
    """封面生成器 - 使用百炼通义万相"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("BAILIAN_API_KEY")
        if not self.api_key:
            raise ValueError(
                "BAILIAN_API_KEY is required. "
                "Please set the BAILIAN_API_KEY environment variable or pass --api-key argument."
            )
        
        # 百炼通义万相 API endpoint
        self.base_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
    
    def generate_cover(
        self,
        prompt: str,
        output_path: str,
        style: str = "photography",
        size: str = "1280*720",
        n: int = 1,
        negative_prompt: str = None
    ) -> bool:
        """
        生成封面图
        
        Args:
            prompt: 封面描述提示词
            output_path: 输出图片路径
            style: 图片风格 (photography, anime, 3d_cartoon, etc.)
            size: 图片尺寸 (1280*720, 1024*1024, 720*1280, etc.)
            n: 生成图片数量
            negative_prompt: 负面提示词（不希望出现的内容）
            
        Returns:
            是否生成成功
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable"  # 使用异步模式
        }
        
        data = {
            "model": "wanx-v1",
            "input": {
                "prompt": prompt
            },
            "parameters": {
                "style": f"<{style}>",  # 百炼 API 要求格式: <style>
                "size": size,
                "n": n
            }
        }
        
        if negative_prompt:
            data["input"]["negative_prompt"] = negative_prompt
        
        try:
            print(f"🎨 正在生成封面...")
            print(f"   提示词: {prompt}")
            print(f"   风格: {style}")
            print(f"   尺寸: {size}")
            
            # 提交任务
            response = requests.post(self.base_url, headers=headers, json=data)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("output"):
                task_id = result["output"]["task_id"]
                task_status = result["output"]["task_status"]
                
                print(f"✓ 任务已提交: {task_id}")
                print(f"   状态: {task_status}")
                
                # 轮询任务状态
                image_url = self._poll_task(task_id, headers)
                
                if image_url:
                    # 下载图片
                    return self._download_image(image_url, output_path)
                else:
                    print("❌ 任务失败")
                    return False
            else:
                print(f"❌ 生成失败: {result}")
                return False
                
        except Exception as e:
            print(f"❌ 生成封面时出错: {e}")
            return False
    
    def _poll_task(self, task_id: str, headers: dict, max_attempts: int = 60) -> Optional[str]:
        """
        轮询任务状态
        
        Args:
            task_id: 任务ID
            headers: 请求头
            max_attempts: 最大轮询次数
            
        Returns:
            图片URL，失败返回None
        """
        # 查询任务的 API 是独立的 GET 请求
        query_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
        
        for attempt in range(max_attempts):
            try:
                time.sleep(2)  # 等待2秒
                
                response = requests.get(query_url, headers=headers)
                response.raise_for_status()
                
                result = response.json()
                task_status = result["output"]["task_status"]
                
                print(f"   轮询 {attempt + 1}/{max_attempts}: {task_status}")
                
                if task_status == "SUCCEEDED":
                    results = result["output"]["results"]
                    if results and len(results) > 0:
                        image_url = results[0]["url"]
                        print(f"✓ 生成成功！")
                        return image_url
                    else:
                        print("❌ 没有生成结果")
                        return None
                
                elif task_status == "FAILED":
                    print(f"❌ 任务失败: {result.get('output', {}).get('message', 'Unknown error')}")
                    return None
                
                # RUNNING 或 PENDING 状态继续等待
                
            except Exception as e:
                print(f"   轮询出错: {e}")
                continue
        
        print("❌ 任务超时")
        return None
    
    def _download_image(self, url: str, output_path: str) -> bool:
        """
        下载图片
        
        Args:
            url: 图片URL
            output_path: 输出路径
            
        Returns:
            是否下载成功
        """
        try:
            print(f"📥 正在下载图片...")
            print(f"   URL: {url}")
            
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            # 确保输出目录存在
            output_dir = os.path.dirname(output_path)
            if output_dir:
                Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"✅ 封面已保存: {output_path}")
            return True
            
        except Exception as e:
            print(f"❌ 下载图片失败: {e}")
            return False


def build_prompt_from_script(script_file: str) -> str:
    """
    从文案文件构建封面提示词
    
    Args:
        script_file: 文案文件路径
        
    Returns:
        封面提示词
    """
    try:
        with open(script_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 提取前几行作为主题参考
        lines = content.split('\n')[:5]
        preview = ' '.join(lines)
        
        # 构建提示词（这里可以进一步优化）
        prompt = f"短视频封面，悬疑侦探风格，{preview[:100]}"
        return prompt
        
    except Exception as e:
        print(f"⚠️  读取文案文件失败: {e}")
        return "短视频封面，悬疑侦探风格"


def main():
    parser = argparse.ArgumentParser(
        description="使用百炼通义万相生成视频封面"
    )
    
    parser.add_argument(
        "-p", "--prompt",
        help="封面描述提示词"
    )
    
    parser.add_argument(
        "-s", "--script",
        help="从文案文件自动生成提示词"
    )
    
    parser.add_argument(
        "-o", "--output",
        default="cover.png",
        help="输出封面路径（默认: cover.png）"
    )
    
    parser.add_argument(
        "--style",
        default="photography",
        choices=["photography", "anime", "3d_cartoon", "oil_painting", "watercolor", "sketch"],
        help="图片风格（默认: photography）"
    )
    
    parser.add_argument(
        "--size",
        default="1280*720",
        choices=["1280*720", "1024*1024", "720*1280", "1920*1080"],
        help="图片尺寸（默认: 1280*720 横版）"
    )
    
    parser.add_argument(
        "-n", "--count",
        type=int,
        default=1,
        help="生成图片数量（默认: 1）"
    )
    
    parser.add_argument(
        "--negative",
        help="负面提示词（不希望出现的内容）"
    )
    
    parser.add_argument(
        "-k", "--api-key",
        help="百炼 API 密钥（可从环境变量 BAILIAN_API_KEY 读取）"
    )
    
    args = parser.parse_args()
    
    # 确定提示词
    if args.prompt:
        prompt = args.prompt
    elif args.script:
        if not os.path.exists(args.script):
            print(f"❌ 错误: 文案文件不存在 → {args.script}")
            return 1
        prompt = build_prompt_from_script(args.script)
    else:
        print("❌ 错误: 请使用 -p 指定提示词或 -s 指定文案文件")
        return 1
    
    print("=" * 80)
    print("视频封面生成器")
    print("=" * 80)
    print(f"提示词: {prompt}")
    print(f"风格: {args.style}")
    print(f"尺寸: {args.size}")
    print(f"输出: {args.output}")
    print("=" * 80)
    
    # 生成封面
    generator = CoverGenerator(api_key=args.api_key)
    success = generator.generate_cover(
        prompt=prompt,
        output_path=args.output,
        style=args.style,
        size=args.size,
        n=args.count,
        negative_prompt=args.negative
    )
    
    if success:
        print("\n✅ 封面生成完成！")
        return 0
    else:
        print("\n❌ 封面生成失败")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
