#!/usr/bin/env python3
"""
从 SRT 字幕文件生成精剪文案脚本
使用 DeepSeek LLM 根据 prompts/1.md 的规则创作短视频文案
"""

import os
import re
import argparse
from pathlib import Path
from typing import List, Dict
from openai import OpenAI


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
    def format_for_llm(subtitles: List[Dict]) -> str:
        """
        将字幕格式化为 LLM 输入格式（带行号）
        
        Returns:
            格式化的字幕文本
        """
        lines = []
        for sub in subtitles:
            lines.append(f"{sub['index']} {sub['text']}")
        return '\n'.join(lines)


class ScriptGenerator:
    """文案生成器 - 使用 DeepSeek LLM"""
    
    def __init__(self, api_key: str = None):
        self.client = OpenAI(
            api_key=api_key or os.getenv("DEEPSEEK_API_KEY") or "sk-b806e7ca03ab4a9cb12445a659349268",
            base_url="https://api.deepseek.com/v1"
        )
    
    def generate_script(self, subtitles_text: str, prompt_file: str = None, 
                       theme: str = None, duration_target: int = None) -> str:
        """
        使用 DeepSeek 生成精剪文案脚本
        
        Args:
            subtitles_text: 格式化的字幕文本（带行号）
            prompt_file: 文案创作规则文件路径（默认 prompts/1.md）
            theme: 视频主题（可选）
            duration_target: 目标时长（秒，可选）
            
        Returns:
            生成的文案脚本
        """
        # 读取创作规则
        prompt_file = prompt_file or "prompts/1.md"
        with open(prompt_file, 'r', encoding='utf-8') as f:
            creation_rules = f.read()
        
        # 构建提示词
        user_prompt = f"""请根据以下字幕内容，创作一篇短视频解说文案。

**原始字幕（带行号）：**
```
{subtitles_text}
```

**创作要求：**
1. 严格按照「[时间] [行号] 内容」格式输出
2. 时间标记表示该段的说话时长（按 5 字/秒计算，50字≈10秒，75字≈15秒）
3. **行号必须是单个连续范围**，格式 [1-50]，不要用 [1-3,5-7] 这种多段格式
4. **每段 60-90 字**，时长 12-18 秒，精炼扼要
5. **尽量多分段**，至少 20-30 段，每段覆盖一个小情节或知识点
6. **段落之间不要有空行**，每段紧密相连，一行一段
7. 开场要有吸引力，设置悬念
8. 故事主线清晰，节奏紧凑
9. 结尾要有升华或收束感
"""
        
        if theme:
            user_prompt += f"\n**视频主题：** {theme}\n"
        
        if duration_target:
            user_prompt += f"\n**目标时长：** 约 {duration_target} 秒（{duration_target // 60}分{duration_target % 60}秒）\n"
        
        user_prompt += """
**示例格式（注意无空行）：**
```
[15s] [1-50] 开场内容，制造悬念，约75字，从第1到50行整合...
[16s] [51-110] 核心卖点，强化冲突，约80字，从第51到110行重组...
[14s] [111-180] 故事推进，设置反转，约70字，从第111到180行提炼...
```

**重要提醒：**
- 行号范围必须是单个连续的 [开始-结束]，不要出现逗号
- 每段时长控制在 12-18 秒，内容精炼
- 段落之间不要有空行，紧密相连
- 多分段，让解说节奏更好

请开始创作："""
        
        try:
            print("🤖 正在调用 DeepSeek 生成文案...")
            
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": f"你是一个专业的短视频文案创作专家。\n\n{creation_rules}"},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=4000
            )
            
            script = response.choices[0].message.content.strip()
            
            # 提取代码块中的内容（如果 LLM 返回了 markdown 代码块）
            code_block_match = re.search(r'```(?:\w+)?\n(.*?)\n```', script, re.DOTALL)
            if code_block_match:
                script = code_block_match.group(1).strip()
            
            print("✅ 文案生成成功！\n")
            return script
            
        except Exception as e:
            print(f"❌ 文案生成失败: {e}")
            raise


def main():
    parser = argparse.ArgumentParser(
        description="从 SRT 字幕生成精剪文案脚本"
    )
    
    parser.add_argument(
        "srt_file",
        help="SRT 字幕文件路径"
    )
    
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="输出文案文件路径"
    )
    
    parser.add_argument(
        "--prompt",
        default="prompts/1.md",
        help="文案创作规则文件（默认: prompts/1.md）"
    )
    
    parser.add_argument(
        "--theme",
        help="视频主题（可选）"
    )
    
    parser.add_argument(
        "--duration",
        type=int,
        help="目标时长（秒，可选）"
    )
    
    parser.add_argument(
        "-k", "--api-key",
        help="DeepSeek API 密钥（可从环境变量 DEEPSEEK_API_KEY 读取）"
    )
    
    args = parser.parse_args()
    
    # 检查文件存在
    if not os.path.exists(args.srt_file):
        print(f"❌ 错误: SRT 文件不存在 → {args.srt_file}")
        return 1
    
    if not os.path.exists(args.prompt):
        print(f"⚠️  警告: 提示词文件不存在 → {args.prompt}，将使用默认规则")
    
    print("=" * 80)
    print("短视频文案生成器")
    print("=" * 80)
    print(f"输入 SRT: {args.srt_file}")
    print(f"输出文案: {args.output}")
    print(f"创作规则: {args.prompt}")
    if args.theme:
        print(f"视频主题: {args.theme}")
    if args.duration:
        print(f"目标时长: {args.duration} 秒")
    print("=" * 80)
    
    # 解析 SRT
    print("\n📄 解析 SRT 字幕...")
    parser_obj = SRTParser()
    subtitles = parser_obj.parse_srt(args.srt_file)
    print(f"✅ 共解析 {len(subtitles)} 条字幕\n")
    
    # 格式化为 LLM 输入
    subtitles_text = parser_obj.format_for_llm(subtitles)
    
    # 生成文案
    generator = ScriptGenerator(api_key=args.api_key)
    script = generator.generate_script(
        subtitles_text=subtitles_text,
        prompt_file=args.prompt,
        theme=args.theme,
        duration_target=args.duration
    )
    
    # 保存文案
    output_dir = os.path.dirname(args.output)
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(script)
    
    print(f"✅ 文案已保存: {args.output}\n")
    
    # 显示预览
    print("=" * 80)
    print("文案预览：")
    print("=" * 80)
    lines = script.split('\n')
    preview_lines = lines[:10] if len(lines) > 10 else lines
    print('\n'.join(preview_lines))
    if len(lines) > 10:
        print(f"\n... (共 {len(lines)} 行，已省略 {len(lines) - 10} 行)")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
