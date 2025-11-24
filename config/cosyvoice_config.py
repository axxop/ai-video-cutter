"""
CosyVoice TTS 配置
支持百练 API 和龙白芷语音模型
"""

import os
from typing import Optional

# ==================== API 配置 ====================

# 百练 API 密钥
BAILIAN_API_KEY = "sk-f0b5e3f543d64b0d8640888cb4327b74"
# 使用阿里云 DashScope API
BAILIAN_API_BASE = "https://dashscope.aliyuncs.com/api/v1"

# ==================== 语音模型配置 ====================

# 龙白芷 - 女性温柔系
VOICE_CONFIG = {
    "dragon_baizhi": {
        "model_id": "cosyvoice-core",  # CosyVoice 核心模型
        "speaker_id": "龙白芷",  # 角色名称
        "voice_id": "龙白芷",  # 语音 ID
        "language": "zh",  # 中文
        "style": "default",
        "description": "龙白芷 - 温柔、亲切的女性声音",
        "sample_rate": 22050,  # Hz
        "format": "wav",  # 输出格式
    },
    # 可扩展的其他语音配置
    "default": {
        "model_id": "cosyvoice-core",
        "speaker_id": "龙白芷",
        "language": "zh",
        "style": "default",
    }
}

# ==================== TTS 参数配置 ====================

TTS_PARAMS = {
    "speed": 1.0,  # 语速：0.5-2.0，1.0 为正常速度
    "pitch": 1.0,  # 音调：0.5-2.0
    "volume": 1.0,  # 音量：0.0-2.0
    "emotion": "neutral",  # 情感：neutral, happy, sad, angry
}

# ==================== 输出配置 ====================

OUTPUT_CONFIG = {
    "output_dir": "p_tts_output/",  # TTS 输出目录
    "format": "wav",  # 输出格式
    "sample_rate": 22050,  # 采样率
    "channels": 1,  # 单声道
}

# ==================== 字符长度和时长映射 ====================

# 基于 5 字/秒的语速标准
# 用于验证 TTS 生成的音频时长是否符合预期
CHAR_TO_DURATION = {
    # 字数 → 预期时长（秒）
    50: 10,    # 50 字 ≈ 10 秒
    75: 15,    # 75 字 ≈ 15 秒
    100: 20,   # 100 字 ≈ 20 秒
}

# ==================== 客户端配置类 ====================

class CosyVoiceConfig:
    """CosyVoice TTS 配置管理类"""
    
    def __init__(
        self,
        api_key: str = BAILIAN_API_KEY,
        api_base: str = BAILIAN_API_BASE,
        speaker_id: str = "龙白芷",
        output_dir: str = OUTPUT_CONFIG["output_dir"],
    ):
        """
        初始化配置
        
        Args:
            api_key: 百练 API 密钥
            api_base: API 基础 URL
            speaker_id: 语音角色 ID
            output_dir: 输出目录
        """
        self.api_key = api_key
        self.api_base = api_base
        self.speaker_id = speaker_id
        self.output_dir = output_dir
        self.voice_config = VOICE_CONFIG.get(speaker_id.lower(), VOICE_CONFIG["default"])
        self.tts_params = TTS_PARAMS.copy()
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
    
    def get_headers(self) -> dict:
        """获取 API 请求头 (DashScope 格式)"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-DashScope-DataInspection": "disable",
        }
    
    def get_voice_config(self) -> dict:
        """获取语音配置"""
        return self.voice_config
    
    def get_tts_params(self) -> dict:
        """获取 TTS 参数"""
        return self.tts_params
    
    def set_speed(self, speed: float):
        """设置语速（0.5-2.0）"""
        if 0.5 <= speed <= 2.0:
            self.tts_params["speed"] = speed
        else:
            raise ValueError("Speed must be between 0.5 and 2.0")
    
    def set_pitch(self, pitch: float):
        """设置音调（0.5-2.0）"""
        if 0.5 <= pitch <= 2.0:
            self.tts_params["pitch"] = pitch
        else:
            raise ValueError("Pitch must be between 0.5 and 2.0")


# ==================== 使用示例 ====================

if __name__ == "__main__":
    # 创建配置实例
    config = CosyVoiceConfig(speaker_id="龙白芷")
    
    print("=== CosyVoice 配置信息 ===")
    print(f"API Key: {config.api_key[:20]}...")
    print(f"API Base: {config.api_base}")
    print(f"Speaker: {config.speaker_id}")
    print(f"Output Dir: {config.output_dir}")
    print(f"\n语音配置: {config.get_voice_config()}")
    print(f"\nTTS 参数: {config.get_tts_params()}")
    print(f"\n请求头: {config.get_headers()}")
