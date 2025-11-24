#!/usr/bin/env python3
"""
从文案文件生成 TTS 音频
支持从 voice_text/*.txt 生成对应的配音音频
"""

import os
import re
import argparse
from pathlib import Path
from typing import List, Tuple, Dict

from config.cosyvoice_config import CosyVoiceConfig
from tts_client import CosyVoiceClient


def parse_script(script_file: str) -> List[Dict]:
    """
    解析文案文件，提取时间、行号和内容
    
    格式: [时间] [行号] 内容
    例如: [10s] [1-3] 这是第一段文案...
    
    Args:
        script_file: 文案文件路径
    
    Returns:
        包含 (time, lines, text) 的列表
    """
    segments = []
    
    with open(script_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            # 解析格式: [时间] [行号] 内容
            match = re.match(r"\[(\d+)s\]\s*\[([^\]]+)\]\s*(.+)", line)
            if match:
                duration = int(match.group(1))
                line_nums = match.group(2)
                text = match.group(3)
                
                segments.append({
                    "duration": duration,
                    "line_nums": line_nums,
                    "text": text,
                })
            else:
                print(f"⚠ 警告: 无法解析行 → {line}")
    
    return segments


def generate_tts(
    script_file: str,
    output_dir: str = "p_tts_output/",
    speaker_id: str = "龙白芷",
    api_key: str = None,
) -> Dict:
    """
    从文案文件生成 TTS 音频
    
    Args:
        script_file: 文案文件路径
        output_dir: 输出目录
        speaker_id: 语音角色 ID
        api_key: 百练 API 密钥
    
    Returns:
        生成结果统计
    """
    # 初始化配置和客户端
    api_key = api_key or os.getenv("BAILIAN_API_KEY")
    config = CosyVoiceConfig(
        api_key=api_key,
        speaker_id=speaker_id,
        output_dir=output_dir,
    )
    client = CosyVoiceClient(config)
    
    # 解析文案
    print(f"📄 解析文案文件: {script_file}")
    segments = parse_script(script_file)
    print(f"✓ 共解析 {len(segments)} 个段落\n")
    
    if not segments:
        print("✗ 文案文件为空或格式不正确")
        return {"total": 0, "success": 0, "failed": 0, "results": []}
    
    # 准备 TTS 列表
    tts_items = []
    for i, segment in enumerate(segments, 1):
        base_name = Path(script_file).stem  # 不含扩展名的文件名
        output_file = os.path.join(
            output_dir,
            f"{base_name}_part{i:02d}_[{segment['line_nums']}].wav"
        )
        
        tts_items.append({
            "text": segment["text"],
            "output_file": output_file,
            "duration": segment["duration"],
            "line_nums": segment["line_nums"],
        })
    
    # 批量生成 TTS
    print(f"🎤 开始生成 TTS 音频 ({speaker_id})...\n")
    
    results = []
    for i, item in enumerate(tts_items, 1):
        try:
            print(f"[{i}/{len(tts_items)}] 时长: {item['duration']}s | 行号: {item['line_nums']}")
            print(f"     文本: {item['text'][:60]}...")
            
            result = client.synthesize(
                text=item["text"],
                output_file=item["output_file"],
            )
            
            # 添加元数据
            result["duration"] = item["duration"]
            result["line_nums"] = item["line_nums"]
            results.append(result)
            
            print(f"     ✓ 成功 → {result['output_file']}\n")
        
        except Exception as e:
            print(f"     ✗ 失败 → {e}\n")
            results.append({
                "status": "failed",
                "error": str(e),
                "duration": item["duration"],
                "line_nums": item["line_nums"],
            })
    
    # 统计结果
    success_count = sum(1 for r in results if r.get("status") == "success")
    failed_count = len(results) - success_count
    
    print("=" * 60)
    print(f"📊 TTS 生成完成")
    print(f"   总计: {len(results)} 个段落")
    print(f"   成功: {success_count} ✓")
    print(f"   失败: {failed_count} ✗")
    print("=" * 60)
    
    return {
        "total": len(results),
        "success": success_count,
        "failed": failed_count,
        "results": results,
    }


def merge_audio_list(results: List[Dict], output_file: str = "merged_audio.json"):
    """
    保存 TTS 生成结果列表，用于后续合成
    
    Args:
        results: TTS 生成结果列表
        output_file: 输出 JSON 文件路径
    """
    import json
    
    # 过滤成功的结果
    success_results = [r for r in results if r.get("status") == "success"]
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(success_results, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 音频列表已保存: {output_file}")


# ==================== CLI 主函数 ====================

def main():
    parser = argparse.ArgumentParser(
        description="从文案文件生成 TTS 配音"
    )
    
    parser.add_argument(
        "script_file",
        help="文案文件路径 (如: voice_text/1.txt)"
    )
    
    parser.add_argument(
        "-o", "--output-dir",
        default="p_tts_output/",
        help="输出目录 (默认: p_tts_output/)"
    )
    
    parser.add_argument(
        "-s", "--speaker",
        default="龙白芷",
        help="语音角色 (默认: 龙白芷)"
    )
    
    parser.add_argument(
        "-k", "--api-key",
        help="百练 API 密钥 (可从环境变量 BAILIAN_API_KEY 读取)"
    )
    
    parser.add_argument(
        "-j", "--json-output",
        help="保存音频列表到 JSON 文件"
    )
    
    args = parser.parse_args()
    
    # 检查文件存在
    if not os.path.exists(args.script_file):
        print(f"✗ 错误: 文件不存在 → {args.script_file}")
        return 1
    
    # 生成 TTS
    result = generate_tts(
        script_file=args.script_file,
        output_dir=args.output_dir,
        speaker_id=args.speaker,
        api_key=args.api_key,
    )
    
    # 保存结果列表
    if args.json_output:
        merge_audio_list(result["results"], args.json_output)
    
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
