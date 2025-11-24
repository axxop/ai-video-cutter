# AI 短视频剪辑工作流程

## 概述

本项目通过多个 AI Agent 协作完成从原始视频到精剪短视频的全流程处理。

---

## 工作流程

### 1. 视频转录（Transcription Agent）

**实现状态：** ✅ 使用外部工具（手动）  
**输入：** 原始视频文件  
**输出：** 带时间戳的字幕文件（SRT 格式）

**主要任务：**
- 使用外部语音识别工具（如 Whisper）转录视频
- 生成带时间戳的 SRT 字幕文件
- 保存格式：`{timestamp}.srt` 和 `{timestamp}_plain.md`

**说明：**
- 本项目**不包含**转录功能实现
- 需要用户提前准备好 SRT 文件（放在 `srts/` 目录）
- 推荐工具：Whisper、剪映、讯飞听见等

---

### 2. 内容分析（Analysis Agent）

**实现状态：** ⚠️ 可选步骤（已集成到 Stage 3）  
**输入：** 字幕文件（SRT 格式）  
**输出：** 结构化的行号标注文本

**主要任务：**
- 读取 SRT 字幕内容
- 将每句话编号标注（方便后续引用）
- 输出格式：
  ```
  1 第一句话内容
  2 第二句话内容
  3 第三句话内容
  ...
  ```

**说明：** 
- Stage 3 文案创作会直接读取 SRT，无需单独分析
- `scripts/analyze_transcript.py` 可用于查看字幕内容（可选）

---

### 3. 文案创作（Scriptwriting Agent）

**实现状态：** ✅ 已实现（使用 DeepSeek）  
**输入：** 
- 原始字幕文件（SRT 格式）
- 文案创作规则（`prompts/1.md`）

**输出：** 精剪文案脚本（带时间轴和行号引用）

**主要任务：**
- 读取 SRT 字幕，提取每句话及行号
- 使用 DeepSeek LLM 根据文案创作规则重组内容
- 选取关键句子，过滤冗余信息
- 合并、润色成适合口播的连贯段落
- 标注每段的说话时长和对应的原始行号

**关键脚本：** `generate_script.py`（读取 SRT → DeepSeek 生成文案）

**输出格式示例：**
```
[10s] [1-3] 开场钩子内容，制造悬念...
[12s] [5,8-9] 核心卖点内容，强化冲突...
[15s] [12-16] 故事主线推进，设置反转...
[8s] [20-21] 结尾收束，情感升华...
```

**格式规范：**
- `[时间]`：该段说话时长（按 5 字/秒计算）
- `[行号]`：原始字幕的行号范围（可不连续）
- 内容：重组后的文案，50-80 字/段

---

### 4. 视频片段提取（Clip Extraction Agent）

**实现状态：** ✅ 已实现  
**输入：** 
- 精剪文案脚本（带行号引用）
- 原始视频文件
- 原始字幕时间戳（SRT）

**输出：** 精剪视频片段

**主要任务：**
- 根据文案中的行号反查原始字幕的时间戳
- 从原始视频中提取对应时间段的片段
- 拼接片段生成最终短视频
- 可选：添加转场效果、背景音乐

**关键脚本：** `video_compressor.py`（使用 DeepSeek LLM + FFmpeg）

---

### 5. TTS 配音（Text-to-Speech Agent）

**实现状态：** ✅ 已实现  
**输入：** 精剪文案脚本（纯文本）  
**输出：** 配音音频文件

**主要任务：**
- 读取文案内容（去除时间和行号标记）
- 使用 TTS 模型生成语音
- 根据标注的时长控制语速
- 输出音频文件供后期合成

**关键脚本：** `generate_tts.py`（使用 CosyVoice）  
**输出目录：** `p_tts_output/` 或 `conan_tts_output/`

---

### 6. 视频合成（Composition Agent）

**实现状态：** ✅ 已实现  
**输入：**
- 提取的视频片段
- TTS 配音音频
- 可选：背景音乐、字幕

**输出：** 最终成品短视频

**主要任务：**
- 视频片段与配音同步
- 添加字幕遮罩（如需要）
- 混合背景音乐（调整音量平衡）
- 渲染输出最终视频

**关键脚本：** `video_compressor.py`（视频压缩与合成）

---

## 数据流转示意

```
原始视频 (origin_videos/)
    ↓
[转录] → 字幕文件 (srts/*.srt, srts/*_plain.md)
    ↓
[分析] → 行号标注文本 (examples_voice_text/*.txt)
    ↓
[创作] → 精剪文案脚本 (voice_text/*.txt)
    ↓
    ├→ [提取] → 视频片段 (video_clips/)
    └→ [TTS] → 配音音频 (p_tts_output/)
         ↓
    [合成] → 成品短视频
```

---

## 目录结构说明

```
ai-video-cutter/
├── origin_videos/          # 原始视频素材
├── srts/                   # 转录字幕文件
├── examples_voice_text/    # 分析后的标注文本（示例）
├── voice_text/             # 精剪文案脚本
├── video_clips/            # 提取的视频片段
├── p_tts_output/           # TTS 配音输出
├── conan_tts_output/       # 柯南角色 TTS 输出
├── prompts/                # AI 文案创作规则
│   └── 1.md               # 短视频文案创作 Prompt
├── scripts/                # 辅助脚本
│   └── analyze_transcript.py  # 字幕分析脚本
└── video_compressor.py     # 视频压缩/合成脚本
```

---

## 关键配置

### 文案创作规则 (`prompts/1.md`)

定义了：
- 短视频文案结构（开场、卖点、主线、高潮、结尾）
- 输入输出格式规范
- 语言风格和节奏控制技巧
- 常用句式和情绪词库

### 语速标准

- **5 字/秒**（正常口播速度）
- 50 字 ≈ 10 秒
- 75 字 ≈ 15 秒
- 单段不超过 100 字（20 秒）

---

## 使用示例

### 步骤 1：转录视频（外部工具）
```bash
# 使用 Whisper（推荐）
whisper origin_videos/video.mp4 --output_dir srts/ --output_format srt --language zh

# 或使用其他工具：
# - 剪映（导出 SRT）
# - 讯飞听见
# - 腾讯云 ASR
# - 阿里云智能语音
```

### 步骤 2：分析字幕（可选）
```bash
# 可选：将 SRT 转换为带行号的纯文本（用于参考）
python scripts/analyze_transcript.py srts/1732974958319.srt > examples_voice_text/1.txt
```

### 步骤 3：创作文案（DeepSeek 自动生成）
```bash
# 直接从 SRT 字幕生成精剪文案脚本
export DEEPSEEK_API_KEY="your_api_key"
python generate_script.py srts/1732974958319.srt -o voice_text/1.txt --prompt prompts/1.md

# 输出格式示例：
# [10s] [1-3] 开场钩子内容...
# [12s] [5-9] 核心卖点内容...
```

### 步骤 4：生成 TTS 配音
```bash
export BAILIAN_API_KEY="your_api_key"
python generate_tts.py voice_text/1.txt -o p_tts_output/ -s 龙白芷
```

### 步骤 5：提取片段并合成最终视频
```bash
# video_compressor.py 会自动：
# 1. 根据文案中的行号范围，用 LLM 选择最佳视频片段
# 2. 提取视频片段
# 3. 添加 TTS 配音和字幕
# 4. 合成最终视频

python video_compressor.py timeline.json srts/1732974958319.srt origin_videos/video.mp4 \
    -o final_video.mp4 --clip-dir video_clips -w 4
```

---

## 优化建议

1. **自动化流程**：编写主控脚本串联所有 Agent
2. **并行处理**：多个视频可并行转录和分析
3. **质量控制**：每个环节添加人工审核节点
4. **模板库**：积累优秀文案模板供参考
5. **A/B 测试**：同一素材生成多版本测试效果
