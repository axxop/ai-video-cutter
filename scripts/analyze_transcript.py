#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析转录JSON文件，提取句子
"""

import json
import os


def analyze_transcript(json_file_path):
    """
    分析转录JSON文件，提取并打印所有句子
    
    Args:
        json_file_path: JSON文件路径
    """
    # 读取JSON文件
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"音频文件: {data.get('file_url', 'N/A')}")
    print(f"音频时长: {data['properties']['original_duration_in_milliseconds']} 毫秒")
    print(f"采样率: {data['properties']['original_sampling_rate']} Hz")
    print("\n" + "="*80)
    print("句子列表:")
    print("="*80 + "\n")
    
    # 提取转录内容
    transcripts = data.get('transcripts', [])
    
    for transcript in transcripts:
        channel_id = transcript.get('channel_id', 0)
        sentences = transcript.get('sentences', [])
        
        print(f"频道 {channel_id} - 共 {len(sentences)} 个句子\n")
        
        # 打印每个句子
        for sentence in sentences:
            text = sentence.get('text', '')
            print(text)


def main():
    # JSON文件路径
    json_file = "/home/user/project/ai-video-cutter/microvideo_data/fuck_transcript_raw.json"
    
    if not os.path.exists(json_file):
        print(f"错误: 文件不存在 - {json_file}")
        return
    
    analyze_transcript(json_file)


if __name__ == "__main__":
    main()
