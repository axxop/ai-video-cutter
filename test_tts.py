#!/usr/bin/env python3
"""
CosyVoice TTS 快速泡测脚本
用于快速验证 API 连接和 TTS 功能
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.cosyvoice_config import CosyVoiceConfig, BAILIAN_API_KEY
from tts_client import CosyVoiceClient


def test_connection():
    """测试 API 连接"""
    print("=" * 60)
    print("🧪 测试 1: API 连接")
    print("=" * 60)
    
    try:
        config = CosyVoiceConfig()
        print(f"✓ API Key: {BAILIAN_API_KEY[:20]}...")
        print(f"✓ API Base: {config.api_base}")
        print(f"✓ Speaker: {config.speaker_id}")
        print(f"✓ Output Dir: {config.output_dir}")
        return True
    except Exception as e:
        print(f"✗ 连接失败: {e}")
        return False


def test_simple_tts():
    """测试简单的文本转语音"""
    print("\n" + "=" * 60)
    print("🧪 测试 2: 简单 TTS (10 字)")
    print("=" * 60)
    
    try:
        config = CosyVoiceConfig()
        client = CosyVoiceClient(config)
        
        text = "大家好，我是龙白芷。"
        print(f"📝 输入文本: {text}")
        print(f"   字数: {len(text)}")
        
        result = client.synthesize(text)
        
        if result["status"] == "success":
            file_size = result.get("file_size", 0)
            print(f"✓ 生成成功")
            print(f"   输出: {result['output_file']}")
            print(f"   大小: {file_size} 字节")
            return True
        else:
            print(f"✗ 生成失败: {result}")
            return False
    
    except Exception as e:
        print(f"✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_medium_tts():
    """测试中等长度的文本转语音"""
    print("\n" + "=" * 60)
    print("🧪 测试 3: 中等 TTS (50 字，约 10 秒)")
    print("=" * 60)
    
    try:
        config = CosyVoiceConfig()
        client = CosyVoiceClient(config)
        
        text = "这是一个测试文案。大家好，我是龙白芷。这是一个短视频配音示例，希望大家喜欢。"
        print(f"📝 输入文本: {text}")
        print(f"   字数: {len(text)}")
        print(f"   预期时长: {len(text) / 5:.1f} 秒")
        
        result = client.synthesize(text)
        
        if result["status"] == "success":
            print(f"✓ 生成成功")
            print(f"   输出: {result['output_file']}")
            print(f"   大小: {result.get('file_size', 0)} 字节")
            return True
        else:
            print(f"✗ 生成失败: {result}")
            return False
    
    except Exception as e:
        print(f"✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_batch_tts():
    """测试批量文本转语音"""
    print("\n" + "=" * 60)
    print("🧪 测试 4: 批量 TTS (3 段文案)")
    print("=" * 60)
    
    try:
        config = CosyVoiceConfig()
        client = CosyVoiceClient(config)
        
        texts = [
            "开场钩子，制造悬念，让观众继续看下去。",
            "核心卖点，强化冲突，说明这一集为什么值得看。",
            "故事主线，推进剧情，设置反转和高潮。",
        ]
        
        print(f"📝 输入文本数: {len(texts)}")
        for i, text in enumerate(texts, 1):
            print(f"   [{i}] {text} ({len(text)} 字)")
        
        results = client.batch_synthesize(texts)
        
        success = sum(1 for r in results if r.get("status") == "success")
        failed = len(results) - success
        
        print(f"\n✓ 批量生成完成")
        print(f"   成功: {success}/{len(results)}")
        print(f"   失败: {failed}/{len(results)}")
        
        for i, result in enumerate(results, 1):
            if result["status"] == "success":
                print(f"   [{i}] ✓ {result['output_file']}")
            else:
                print(f"   [{i}] ✗ {result.get('error', 'Unknown error')}")
        
        return failed == 0
    
    except Exception as e:
        print(f"✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_long_text():
    """测试较长文本转语音（模拟实际使用）"""
    print("\n" + "=" * 60)
    print("🧪 测试 5: 长文本 TTS (约 75 字，15 秒)")
    print("=" * 60)
    
    try:
        config = CosyVoiceConfig()
        client = CosyVoiceClient(config)
        
        text = "万万没想到，事情竟然会发展成这样。这个故事从开始就充满了悬念，随后发生的一切都让人目瞪口呆。出乎意料的是，真相竟然是这样。现在让我们一起来看看更离谱的部分吧。"
        
        print(f"📝 输入文本: {text}")
        print(f"   字数: {len(text)}")
        print(f"   预期时长: {len(text) / 5:.1f} 秒")
        
        result = client.synthesize(text)
        
        if result["status"] == "success":
            print(f"✓ 生成成功")
            print(f"   输出: {result['output_file']}")
            print(f"   大小: {result.get('file_size', 0)} 字节")
            return True
        else:
            print(f"✗ 生成失败: {result}")
            return False
    
    except Exception as e:
        print(f"✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有泡测"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 58 + "║")
    print("║" + "  🎤 CosyVoice TTS 快速泡测".center(58) + "║")
    print("║" + " " * 58 + "║")
    print("╚" + "=" * 58 + "╝")
    
    results = []
    
    # 运行测试
    results.append(("API 连接", test_connection()))
    results.append(("简单 TTS", test_simple_tts()))
    results.append(("中等 TTS", test_medium_tts()))
    results.append(("批量 TTS", test_batch_tts()))
    results.append(("长文本 TTS", test_long_text()))
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {name}")
    
    print("\n" + "-" * 60)
    print(f"总计: {passed}/{total} 个测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！CosyVoice TTS 已就绪。")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败，请检查配置或 API。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
