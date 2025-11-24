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
    def parse_srt(srt_file: str, start_time: float = None, end_time: float = None) -> List[Dict]:
        """
        解析 SRT 字幕文件
        
        Args:
            srt_file: SRT文件路径
            start_time: 起始时间（秒），只解析此时间之后的字幕
            end_time: 结束时间（秒），只解析此时间之前的字幕
        
        Returns:
            字幕列表，每个字幕包含 index, start_time, end_time, text
        """
        subtitles = []
        
        with open(srt_file, 'r', encoding='utf-8-sig') as f:  # utf-8-sig 自动去除BOM
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
                    
                    sub_start_time = start_h * 3600 + start_m * 60 + start_s + start_ms / 1000
                    sub_end_time = end_h * 3600 + end_m * 60 + end_s + end_ms / 1000
                    
                    # 过滤时间范围
                    if start_time is not None and sub_end_time < start_time:
                        continue
                    if end_time is not None and sub_start_time > end_time:
                        continue
                    
                    subtitles.append({
                        'index': index,
                        'start_time': sub_start_time,
                        'end_time': sub_end_time,
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
2. 时间标记表示该段的说话时长（按 5 字/秒计算，15字≈3秒，25字≈5秒）
3. **行号必须是单个连续范围**，格式 [1-8]，不要用 [1-3,5-7] 这种多段格式
4. **每段 15-30 字**，时长 3-6 秒，简短精炼
5. **每段覆盖 5-12 行字幕**，让视频片段更短更精准
6. **尽量多分段**，至少 80-120 段，每段对应一个具体画面或短句
7. **段落之间不要有空行**，每段紧密相连，一行一段
8. **关键要求：每段文案必须包含对应字幕行中的关键词、人名、对话或场景**
9. 解说可以润色、总结、扩展，但核心关键词必须来自字幕原文
10. 这样LLM才能通过关键词匹配到正确的视频片段
11. ⚠️ **跳过片头旁白和歌词**：如果字幕包含动漫片头旁白（如「我是XX，身体虽小...真相永远只有一个」）或歌词，必须跳过这些行号，从正片剧情内容开始创作文案
12. ⚠️ **不要使用歌词或片头旁白内容**：文案中不能出现歌词或片头固定台词
"""
        
        if theme:
            user_prompt += f"\n**视频主题：** {theme}\n"
        
        if duration_target:
            user_prompt += f"\n**目标时长：** 约 {duration_target} 秒（{duration_target // 60}分{duration_target % 60}秒）\n"
        
        user_prompt += """
**示例格式（注意无空行，短片段，包含字幕关键词）：**
```
[3s] [1-5] 怪盗基德发出预告信！要偷两把肋差刀
[4s] [6-10] 斧江财团戒备森严，柯南已到场
[5s] [11-18] 基德22小时前就偷了！
[4s] [19-25] 斧江家创始人痴迷土方岁三
[5s] [26-32] 收藏了大量相关物品
```

**重要提醒：**
- 行号范围必须是单个连续的 [开始-结束]，不要出现逗号
- 每段时长控制在 3-6 秒，内容简短精炼
- 每段覆盖 5-12 行字幕，让片段更短更精准
- 段落之间不要有空行，紧密相连
- 多分段（至少 80-120 段），让解说节奏更快更碎片化
- **文案中的关键词（人名、地点、对话）必须来自对应行号的字幕，确保可追溯**

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
    
    parser.add_argument(
        "--start",
        type=float,
        help="起始时间（秒），只处理此时间之后的字幕"
    )
    
    parser.add_argument(
        "--end",
        type=float,
        help="结束时间（秒），只处理此时间之前的字幕"
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
    if args.start or args.end:
        time_range = f" (时间范围: {args.start or 0}s - {args.end or '结束'}s)"
        print(f"   {time_range}")
    parser_obj = SRTParser()
    subtitles = parser_obj.parse_srt(args.srt_file, start_time=args.start, end_time=args.end)
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
