# AI 短视频剪辑工作流程

## 概述

本项目通过多个 AI Agent 协作完成从原始视频到精剪短视频的全流程处理。

---

## 工作流程

### 1. 视频转录（Transcription Agent）

**输入：** 原始视频文件  
**输出：** 带时间戳的字幕文件（SRT 格式）

**主要任务：**
- 提取视频音频轨道
- 使用语音识别模型转录为文字
- 生成带时间戳的字幕文件
- 保存格式：`{timestamp}.srt` 和 `{timestamp}_plain.md`

---

### 2. 内容分析（Analysis Agent）

**输入：** 字幕文件（纯文本格式）  
**输出：** 结构化的行号标注文本

**主要任务：**
- 读取转录字幕内容
- 将每句话编号标注（方便后续引用）
- 输出格式：
  ```
  1 第一句话内容
  2 第二句话内容
  3 第三句话内容
  ...
  ```

**关键脚本：** `scripts/analyze_transcript.py`

---

### 3. 文案创作（Scriptwriting Agent）

**输入：** 
- 标注好行号的字幕文本
- 文案创作规则（`prompts/1.md`）

**输出：** 精剪文案脚本（带时间轴和行号引用）

**主要任务：**
- 根据短视频文案创作规则重组内容
- 选取关键句子，过滤冗余信息
- 合并、润色成适合口播的连贯段落
- 标注每段的说话时长和对应的原始行号

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

**关键工具：** FFmpeg、视频编辑库

---

### 5. TTS 配音（Text-to-Speech Agent）

**输入：** 精剪文案脚本（纯文本）  
**输出：** 配音音频文件

**主要任务：**
- 读取文案内容（去除时间和行号标记）
- 使用 TTS 模型生成语音
- 根据标注的时长控制语速
- 输出音频文件供后期合成

**输出目录：** `p_tts_output/` 或 `conan_tts_output/`

---

### 6. 视频合成（Composition Agent）

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

### 步骤 1：转录视频
```bash
# 使用 Whisper 或其他语音识别工具
whisper origin_videos/video.mp4 --output_dir srts/ --output_format srt
```

### 步骤 2：分析字幕
```bash
python scripts/analyze_transcript.py srts/video_plain.md > examples_voice_text/1.txt
```

### 步骤 3：创作文案
```
使用 AI（如 GPT-4）+ prompts/1.md 规则
输入：examples_voice_text/1.txt
输出：voice_text/1.txt
```

### 步骤 4：提取片段 + TTS + 合成
```bash
# 根据 voice_text/1.txt 提取视频片段
# 生成 TTS 配音
# 使用 video_compressor.py 合成最终视频
python video_compressor.py --input video_clips/ --audio p_tts_output/ --output final.mp4
```

---

## 优化建议

1. **自动化流程**：编写主控脚本串联所有 Agent
2. **并行处理**：多个视频可并行转录和分析
3. **质量控制**：每个环节添加人工审核节点
4. **模板库**：积累优秀文案模板供参考
5. **A/B 测试**：同一素材生成多版本测试效果
