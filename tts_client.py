"""
CosyVoice TTS 客户端
使用阿里云 DashScope SDK 进行文本转语音
"""

import os
import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat
from typing import Optional
from pathlib import Path
import logging

from config.cosyvoice_config import CosyVoiceConfig

# 日志配置
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CosyVoiceClient:
    """CosyVoice TTS 客户端"""
    
    def __init__(self, config: CosyVoiceConfig):
        """
        初始化客户端
        
        Args:
            config: CosyVoiceConfig 配置实例
        """
        self.config = config
        # 检查 API key 是否有效
        if not config.api_key:
            raise ValueError(
                "BAILIAN_API_KEY is required. "
                "Please set the BAILIAN_API_KEY environment variable or pass it to CosyVoiceConfig."
            )
        # 设置 DashScope API Key
        dashscope.api_key = config.api_key
    
    def synthesize(
        self,
        text: str,
        output_file: Optional[str] = None,
        speaker_id: Optional[str] = None,
    ) -> dict:
        """
        将文本转换为语音
        
        Args:
            text: 输入文本
            output_file: 输出文件路径（可选，不指定则使用默认命名）
            speaker_id: 语音角色 ID（可选，使用配置中的默认值）
        
        Returns:
            包含音频文件路径和元数据的字典
        """
        if not text:
            raise ValueError("Text cannot be empty")
        
        speaker_id = speaker_id or self.config.speaker_id
        
        try:
            logger.info(f"正在合成语音: {speaker_id} | 文本长度: {len(text)} 字")
            
            # 创建合成器
            synthesizer = SpeechSynthesizer(
                model='cosyvoice-v2',
                # voice='longhua_v2',  # 标准女声
                voice='longbaizhi',  # 标准女声
                format=AudioFormat.WAV_22050HZ_MONO_16BIT,
            )
            
            # 调用合成 (同步)
            audio_data = synthesizer.call(text)
            
            if audio_data is None:
                error_msg = f"TTS 合成失败: 返回数据为空"
                logger.error(error_msg)
                raise Exception(error_msg)
            
            # 生成输出文件名
            if not output_file:
                output_file = os.path.join(
                    self.config.output_dir,
                    f"tts_{hash(text) % 10000000}_{speaker_id}.wav"
                )
            
            # 确保输出目录存在
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            
            # 保存音频文件
            with open(output_file, "wb") as f:
                f.write(audio_data)
            
            logger.info(f"✓ 语音合成成功: {output_file}")
            
            return {
                "status": "success",
                "output_file": output_file,
                "text_length": len(text),
                "speaker": speaker_id,
                "file_size": os.path.getsize(output_file),
            }
        
        except Exception as e:
            logger.error(f"✗ 错误: {e}")
            raise
    
    def batch_synthesize(
        self,
        texts: list,
        output_dir: Optional[str] = None,
        speaker_id: Optional[str] = None,
    ) -> list:
        """
        批量文本转语音
        
        Args:
            texts: 文本列表，每项可以是字符串或 dict {"text": "...", "output_file": "..."}
            output_dir: 输出目录
            speaker_id: 语音角色 ID
        
        Returns:
            结果列表
        """
        results = []
        output_dir = output_dir or self.config.output_dir
        
        logger.info(f"开始批量合成: {len(texts)} 个文本")
        
        for i, item in enumerate(texts, 1):
            try:
                if isinstance(item, dict):
                    text = item.get("text", "")
                    output_file = item.get("output_file")
                else:
                    text = item
                    output_file = None
                
                result = self.synthesize(text, output_file, speaker_id)
                results.append(result)
                logger.info(f"[{i}/{len(texts)}] ✓ 完成")
            
            except Exception as e:
                logger.error(f"[{i}/{len(texts)}] ✗ 失败: {e}")
                results.append({
                    "status": "failed",
                    "error": str(e),
                })
        
        logger.info(f"批量合成完成: {sum(1 for r in results if r['status'] == 'success')}/{len(texts)}")
        return results


# ==================== 便利函数 ====================

def tts(
    text: str,
    speaker: str = "龙白芷",
    api_key: Optional[str] = None,
    output_file: Optional[str] = None,
) -> str:
    """
    快速 TTS 函数
    
    Args:
        text: 输入文本
        speaker: 语音角色
        api_key: API 密钥（使用环境变量或配置中的默认值）
        output_file: 输出文件路径
    
    Returns:
        输出文件路径
    """
    api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
    config = CosyVoiceConfig(api_key=api_key, speaker_id=speaker)
    client = CosyVoiceClient(config)
    result = client.synthesize(text, output_file)
    
    if result["status"] == "success":
        return result["output_file"]
    else:
        raise Exception(f"TTS 失败: {result}")


# ==================== 使用示例 ====================

if __name__ == "__main__":
    # 创建配置和客户端
    config = CosyVoiceConfig(speaker_id="龙白芷")
    client = CosyVoiceClient(config)
    
    # 示例文本
    text = "大家好，我是龙白芷。这是一个短视频配音示例。"
    
    # 单个文本转语音
    print("=== 单个文本转语音 ===")
    try:
        result = client.synthesize(text)
        print(f"结果: {result}")
    except Exception as e:
        print(f"错误: {e}")
    
    # 批量文本转语音
    print("\n=== 批量文本转语音 ===")
    texts = [
        "开场钩子，制造悬念...",
        "核心卖点，强化冲突...",
        "故事主线，推进剧情...",
    ]
    
    try:
        results = client.batch_synthesize(texts)
        for i, result in enumerate(results, 1):
            print(f"[{i}] {result}")
    except Exception as e:
        print(f"错误: {e}")
    
    # 使用便利函数
    print("\n=== 使用便利函数 ===")
    try:
        output = tts("快速示例文本", speaker="龙白芷")
        print(f"生成的文件: {output}")
    except Exception as e:
        print(f"错误: {e}")
