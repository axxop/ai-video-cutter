# 故障排查指南

## 问题: `generate_video.py` 运行时卡死或失败

### 常见原因和解决方案

#### 1. 缺少 API Keys（最常见）

**症状:**
```
ERROR:tts_client:✗ 错误: can only concatenate str (not "NoneType") to str
TTS 生成失败: can only concatenate str (not "NoneType") to str
```

或者:
```
openai.OpenAIError: The api_key client option must be set either by passing api_key to the client or by setting the OPENAI_API_KEY environment variable
```

**原因:**
- 缺少 `BAILIAN_API_KEY` 环境变量（用于 TTS）
- 缺少 `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY` 环境变量（用于视频片段选择）

**解决方案:**

**方法 1: 使用提供的运行脚本（推荐）**
```fish
./run_generate_video.sh voice_text/generated_script_v3.txt srts/1732974958319.srt origin_videos/1732974958319.mp4 -o final_video.mp4 --tts-workers 4 --clip-workers 3 --video-workers 3
```

**方法 2: 手动设置环境变量**
```fish
# Fish shell
set -x BAILIAN_API_KEY "sk-f0b5e3f543d64b0d8640888cb4327b74"
set -x DEEPSEEK_API_KEY "sk-b806e7ca03ab4a9cb12445a659349268"

# 然后运行
python generate_video.py voice_text/generated_script_v3.txt srts/1732974958319.srt origin_videos/1732974958319.mp4 -o final_video.mp4
```

**方法 3: 创建 .env 文件**
```bash
# 在项目根目录创建 .env 文件
echo 'BAILIAN_API_KEY=sk-f0b5e3f543d64b0d8640888cb4327b74' >> .env
echo 'DEEPSEEK_API_KEY=sk-b806e7ca03ab4a9cb12445a659349268' >> .env

# 使用 fish 加载
source .env
```

---

#### 2. TTS 并发失败

**症状:**
- 大量 TTS 生成失败
- `✅ TTS 生成完成: 0 个音频（0 个来自缓存）`

**原因:**
- API 限流
- 网络问题
- 文本格式问题

**解决方案:**
```fish
# 降低 TTS 并发数
python generate_video.py ... --tts-workers 2

# 或者使用缓存，重新运行会跳过已生成的部分
python generate_video.py ... --cache-dir .cache
```

---

#### 3. 视频片段选择失败

**症状:**
- `⚠️ 跳过片段：调整后行号为负数`
- `⚠ 行号范围内没有找到字幕`

**原因:**
- 字幕文件和脚本文件的行号不匹配
- 脚本中的行号范围超出字幕范围

**解决方案:**
1. 检查脚本文件格式是否正确：
   ```
   [15s] [1-50] 内容文本...
   [20s] [51-100] 内容文本...
   ```

2. 确认字幕文件行号范围:
   ```fish
   wc -l srts/1732974958319.srt
   ```

3. 调整脚本中的行号范围

---

#### 4. 程序完全卡死（无输出）

**症状:**
- 程序启动后无任何输出
- CPU 使用率很低

**可能原因:**
- 等待 API 响应超时
- 网络连接问题
- ffmpeg 进程卡住

**解决方案:**
```fish
# 1. 检查网络连接
ping api.deepseek.com
ping dashscope.aliyuncs.com

# 2. 降低并发数（减少同时进行的任务）
python generate_video.py ... --tts-workers 1 --clip-workers 1 --video-workers 1

# 3. 清理缓存重新开始
rm -rf .cache
python generate_video.py ... --force-clean
```

---

#### 5. 内存不足或 ffmpeg 错误

**症状:**
- `MemoryError`
- ffmpeg 进程崩溃
- `提取失败: ...`

**解决方案:**
```fish
# 降低视频处理并发数
python generate_video.py ... --video-workers 1

# 检查磁盘空间
df -h

# 检查 ffmpeg 是否正常工作
ffmpeg -version
```

---

## 推荐的运行流程

### 首次运行（测试）
```fish
# 1. 设置环境变量
set -x BAILIAN_API_KEY "sk-f0b5e3f543d64b0d8640888cb4327b74"
set -x DEEPSEEK_API_KEY "sk-b806e7ca03ab4a9cb12445a659349268"

# 2. 使用最低并发数测试
python generate_video.py \
  voice_text/generated_script_v3.txt \
  srts/1732974958319.srt \
  origin_videos/1732974958319.mp4 \
  -o final_video.mp4 \
  --tts-workers 1 \
  --clip-workers 1 \
  --video-workers 1
```

### 正式运行（生产）
```fish
# 确认测试通过后，使用更高的并发数
./run_generate_video.sh \
  voice_text/generated_script_v3.txt \
  srts/1732974958319.srt \
  origin_videos/1732974958319.mp4 \
  -o final_video.mp4 \
  --tts-workers 4 \
  --clip-workers 3 \
  --video-workers 3
```

---

## 调试技巧

### 查看详细日志
```fish
# Python 详细日志
python -v generate_video.py ...

# 查看 ffmpeg 输出（修改脚本中的 -loglevel error 为 -loglevel info）
```

### 检查缓存
```fish
# 查看缓存目录结构
tree .cache

# 查看已生成的 TTS 文件
ls -lh .cache/tts/

# 查看已生成的视频片段
ls -lh .cache/clips/
```

### 手动测试单个步骤

**测试 TTS:**
```fish
set -x BAILIAN_API_KEY "sk-f0b5e3f543d64b0d8640888cb4327b74"
python test_tts.py
```

**测试 DeepSeek API:**
```fish
set -x DEEPSEEK_API_KEY "sk-b806e7ca03ab4a9cb12445a659349268"
python -c "from openai import OpenAI; client = OpenAI(api_key='$DEEPSEEK_API_KEY', base_url='https://api.deepseek.com/v1'); print(client.models.list())"
```

---

## 联系支持

如果以上方法都无法解决问题，请提供：
1. 完整的错误信息
2. 运行的命令
3. 环境信息（Python 版本、ffmpeg 版本、操作系统）
4. 相关日志文件
