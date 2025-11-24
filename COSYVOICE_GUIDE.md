# CosyVoice TTS 使用指南

## 快速开始

### 1. 环境配置

**设置 API 密钥：**
```bash
export BAILIAN_API_KEY="sk-f0b5e3f543d64b0d8640888cb4327b74"
```

或在代码中直接配置（不推荐提交代码库）。

### 2. 安装依赖

```bash
pip install requests
```

### 3. 文件结构

```
ai-video-cutter/
├── config/
│   └── cosyvoice_config.py      # CosyVoice 配置文件
├── tts_client.py                 # TTS 客户端库
├── generate_tts.py               # TTS 生成脚本
├── voice_text/                   # 输入文案文件
│   └── 1.txt                     # 精剪文案（格式见下）
└── p_tts_output/                 # 输出音频目录
```

---

## 使用方法

### 方法一：命令行生成（推荐）

**基本用法：**
```bash
python generate_tts.py voice_text/1.txt
```

**带参数的完整用法：**
```bash
python generate_tts.py voice_text/1.txt \
  -o p_tts_output/ \
  -s 龙白芷 \
  -k sk-f0b5e3f543d64b0d8640888cb4327b74 \
  -j audio_list.json
```

**参数说明：**
- `voice_text/1.txt` - 输入文案文件路径
- `-o, --output-dir` - 输出目录（默认：p_tts_output/）
- `-s, --speaker` - 语音角色（默认：龙白芷）
- `-k, --api-key` - API 密钥（可省略，使用环境变量）
- `-j, --json-output` - 保存音频列表到 JSON 文件

### 方法二：Python 代码调用

**快速调用（函数式）：**
```python
from tts_client import tts

# 生成单个语音
output_file = tts(
    text="大家好，我是龙白芷。",
    speaker="龙白芷"
)
print(f"生成: {output_file}")
```

**详细调用（面向对象）：**
```python
from config.cosyvoice_config import CosyVoiceConfig
from tts_client import CosyVoiceClient

# 创建配置
config = CosyVoiceConfig(speaker_id="龙白芷")

# 创建客户端
client = CosyVoiceClient(config)

# 单个文本转语音
result = client.synthesize(
    text="这是一个测试文本。",
    output_file="output.wav"
)

print(f"状态: {result['status']}")
print(f"文件: {result['output_file']}")
```

**批量生成：**
```python
texts = [
    "第一段文案...",
    "第二段文案...",
    "第三段文案...",
]

results = client.batch_synthesize(texts)

for result in results:
    print(result)
```

---

## 文案文件格式

### 输入格式（voice_text/1.txt）

每行一个段落，格式为：`[时间] [行号] 内容`

**示例：**
```
[10s] [1-3] 大家好，这是一个短视频开场钩子，用来制造悬念。
[12s] [5,8-9] 出乎意料的是，事情竟然发展成了这样。
[15s] [12-16] 随后的故事更加离谱，让我们继续看下去。
[8s] [20-21] 最后的反转让人目瞪口呆。
```

**格式要求：**
- `[时间]` - 段落的说话时长（秒），按 5 字/秒计算
- `[行号]` - 原始字幕的行号范围（可不连续）
- `内容` - 重组后的口播文案（50-80 字为佳）

### 输出格式

每个段落生成一个 WAV 文件，命名规则：
```
{script_name}_part{序号:02d}_[{行号}].wav
```

**示例：**
```
p_tts_output/
├── 1_part01_[1-3].wav
├── 1_part02_[5,8-9].wav
├── 1_part03_[12-16].wav
└── 1_part04_[20-21].wav
```

---

## 配置调整

### 修改语速

```python
from config.cosyvoice_config import CosyVoiceConfig

config = CosyVoiceConfig()
config.set_speed(1.2)  # 快速：1.2x
config.set_speed(0.8)  # 慢速：0.8x
```

**语速范围：** 0.5 ~ 2.0（推荐 0.8 ~ 1.2）

### 修改音调

```python
config.set_pitch(1.1)  # 提高音调 10%
config.set_pitch(0.9)  # 降低音调 10%
```

**音调范围：** 0.5 ~ 2.0

### 其他参数

在 `config/cosyvoice_config.py` 的 `TTS_PARAMS` 中修改：

```python
TTS_PARAMS = {
    "speed": 1.0,        # 语速
    "pitch": 1.0,        # 音调
    "volume": 1.0,       # 音量
    "emotion": "neutral", # 情感：neutral, happy, sad, angry
}
```

---

## 错误处理

### 常见问题

**1. API 密钥无效**
```
✗ API 错误: 401 - Unauthorized
```
→ 检查 `BAILIAN_API_KEY` 环境变量是否正确设置

**2. 文件不存在**
```
✗ 错误: 文件不存在 → voice_text/1.txt
```
→ 确保文案文件存在于 `voice_text/` 目录

**3. 解析错误**
```
⚠ 警告: 无法解析行 → [invalid format]
```
→ 检查文案格式是否符合 `[时间] [行号] 内容`

### 调试模式

启用详细日志：
```python
import logging

logging.basicConfig(level=logging.DEBUG)
```

---

## 完整工作流示例

```bash
# 1. 设置 API 密钥
export BAILIAN_API_KEY="sk-f0b5e3f543d64b0d8640888cb4327b74"

# 2. 创建文案文件（voice_text/demo.txt）
cat > voice_text/demo.txt << 'EOF'
[10s] [1-3] 大家好，我是龙白芷。这是一个短视频配音示例。
[12s] [5-8] 我们将学习如何使用 CosyVoice TTS 生成自然流畅的语音。
[8s] [10-12] 希望大家喜欢，谢谢观看！
EOF

# 3. 生成 TTS 音频
python generate_tts.py voice_text/demo.txt -o p_tts_output/ -j audio_list.json

# 4. 查看生成的音频
ls -la p_tts_output/

# 5. 音频列表已保存到 audio_list.json，可用于后续视频合成
cat audio_list.json
```

---

## 与视频编辑流程集成

生成的音频文件可直接用于视频合成：

```python
from video_compressor import VideoComposer

composer = VideoComposer(
    video_clips_dir="video_clips/",
    audio_list="audio_list.json",  # 由 generate_tts.py 生成
    output_file="final_video.mp4"
)

composer.compose()
```

---

## 成本估算

- 百练 API 按 API 调用次数和音频时长计费
- 建议在开发阶段先用小样本测试
- 批量生成时使用 `batch_synthesize()` 更高效

---

## 支持的语音角色

当前配置支持的角色：
- **龙白芷** - 温柔、亲切的女性声音（推荐用于解说）

可在 `config/cosyvoice_config.py` 的 `VOICE_CONFIG` 中扩展更多角色。

---

## 更多信息

- 百练官方文档: https://bailian.aliyun.com
- CosyVoice GitHub: https://github.com/alibaba-damo-academy/CosyVoice
