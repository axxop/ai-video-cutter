#!/usr/bin/env python3
"""
从 SRT 字幕文件生成精剪文案脚本 V2
在文案中嵌入行号标记，明确标注关键词来源
格式: 文本内容[行号范围]更多文本[行号范围]...
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


class ScriptGeneratorV2:
    """文案生成器 V2 - 使用 DeepSeek LLM，嵌入行号标记"""
    
    def __init__(self, api_key: str = None):
        self.client = OpenAI(
            api_key=api_key or os.getenv("DEEPSEEK_API_KEY") or "sk-b806e7ca03ab4a9cb12445a659349268",
            base_url="https://api.deepseek.com/v1"
        )
    
    def generate_script(self, subtitles_text: str, prompt_file: str = None, 
                       theme: str = None, duration_target: int = None) -> str:
        """
        使用 DeepSeek 生成带行号标记的精剪文案脚本
        
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
        user_prompt = f"""请根据以下字幕内容，创作一篇完整的短视频解说文案。

**原始字幕（带行号）：**
```
{subtitles_text}
```

**创作要求（V2格式 - 强化版）：**

🎯 **开头钩子（前20-30秒，必须极具吸引力）：**
- 必须以**最震撼/最悬疑/最戏剧性**的情节开场
- 使用**反转、冲突、悬念、惊人事实**等手法
- 可以用：
  * "你绝对想不到..." / "令所有人震惊的是..."
  * "深夜0点[X-Y]，价值百万的宝藏突然消失..."
  * "他早在22小时前[X-Y]就完成了不可能的偷盗..."
  * "这个看似普通的物品[X-Y]，竟然关系到150年前的秘密..."
- 前3句话必须让观众产生"必须看下去"的冲动
- 可以打乱时间线，从最精彩的部分开始讲述

⏱️ **关键时长要求（避免解说卡顿）：**
- TTS语速约为 **6字/秒**（这是固定的朗读速度）
- 每标注一个关键词[行号范围]，该范围的字幕必须提供足够的视频时长
- **公式**: 如果你写了30个字，需要30÷6=5秒视频，所以行号范围必须覆盖至少5秒的字幕内容
- 标注的行号范围不要太短（如[1-3]只有几秒），应该覆盖更多行（如[1-15]可能有8-10秒）
- 宁可行号范围大一些，也不要太小导致视频时长不够

📝 **正文内容（讲述完整故事）：**
1. 创作一篇**完整流畅的解说文案**，不需要分段，不需要标注时间
2. 在文案中的关键词、人名、地点、对话后面用方括号标注字幕行号
3. 格式示例：`怪盗基德[1-15]发出预告信，要偷斧江家[16-30]的两把肋差刀[31-45]，财团戒备森严[46-60]...`
4. **每个标注的行号范围要足够大**，确保有足够视频时长匹配前面的文字
5. **优先保证文案的趣味性和流畅性**，像讲故事一样生动有趣
6. **在保证有趣的基础上**，对关键词标注字幕行号，确保能匹配到对应画面
7. **文案总长度约 1500-2000 字**，充分展开情节，增加细节描述和情绪渲染
8. 不要分段，不要空行，就是一篇连贯的文章

🔍 **内容扩展技巧（确保时长足够）：**
- 增加人物心理描写：角色的想法、疑惑、推理过程
- 增加场景细节：环境氛围、紧张气氛的营造
- 增加对话引用：关键台词的复述（需标注行号）
- 增加悬念铺垫：每个线索发现前的铺垫和思考
- 增加情节转折：强调"但是"、"然而"、"令人意外的是"等转折
- 增加情绪词汇：震惊、惊讶、恐慌、紧张、不可思议等

**格式说明：**
- `关键词[行号范围]`：关键词后面紧跟其来源的字幕行号
- 行号格式：单个连续范围，如 [1-15]、[20-45]、[100-130]
- **行号范围要足够大**：按6字/秒语速，30字需要5秒，可能需要覆盖10-20行字幕
- 不需要标注每个词，只标注重要的人名、地点、对话、关键事件
- 优先考虑文案的故事性和吸引力

**示例格式（正确 - 含强力钩子 + 充足行号范围）：**
```
你绝对想不到[1-12]，这次怪盗基德[13-25]的预告信竟然是个天大的骗局！当中森警部[350-380]带着上百名警力在深夜0点[10-20]严阵以待时，两把价值连城的肋差刀[45-60]早已消失无踪[63-75]。更令人震惊的是，基德早在22小时前[75-90]就完成了偷盗，这两把看似普通的刀[420-450]，竟然隐藏着150年前新选组副长土方岁三[50-70]留下的惊天秘密[318-340]！时间回到事件开始，名侦探柯南[29-45]和大阪的服部平次[32-48]接到委托，要调查斧江财团[16-35]一起离奇的律师命案[238-260]。被害人久垣澄人[22-38]身上留下了十字刀伤[437-455]，凶器推测是日本刀[252-268]，而他生前正在寻找六把神秘的肋差刀[420-445]...
```

**重要提醒：**
- **开头必须有强力钩子**，前20-30秒抓住观众注意力
- **时长要足够**，1500-2000字，充分展开情节
- **行号范围要大**：每次标注覆盖15-30行，确保5-10秒视频时长，避免解说卡顿
- 优先保证文案生动有趣，像讲故事一样吸引人
- 行号标注是辅助功能，帮助匹配视频画面，但范围必须足够大
- 不要为了标注行号而破坏文案的流畅性
"""
        
        if theme:
            user_prompt += f"\n**视频主题：** {theme}\n"
        
        if duration_target:
            user_prompt += f"\n**目标时长：** 约 {duration_target} 秒（{duration_target // 60}分{duration_target % 60}秒）\n"
        
        user_prompt += "\n请开始创作一篇完整的解说文案（V2格式，不分段，标注关键词行号）："
        
        try:
            print("🤖 正在调用 DeepSeek 生成文案（V2格式）...")
            
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": f"你是一个专业的短视频文案创作专家。\n\n{creation_rules}"},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.8,  # 提高创意性
                max_tokens=6000   # 增加字数上限
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
        description="从 SRT 字幕生成精剪文案脚本 V2（嵌入行号标记）"
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
    print("短视频文案生成器 V2（嵌入行号标记）")
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
    generator = ScriptGeneratorV2(api_key=args.api_key)
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
