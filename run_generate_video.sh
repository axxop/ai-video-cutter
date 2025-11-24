#!/usr/bin/env fish
# 视频生成脚本 - 设置必要的环境变量并运行

# 设置 API Keys（从配置文件读取）
set -x BAILIAN_API_KEY "sk-f0b5e3f543d64b0d8640888cb4327b74"
set -x DEEPSEEK_API_KEY "sk-b806e7ca03ab4a9cb12445a659349268"

# 也设置 OPENAI_API_KEY 作为备选
set -x OPENAI_API_KEY $DEEPSEEK_API_KEY

echo "=============================================="
echo "视频生成工具 - 环境变量已设置"
echo "=============================================="
echo "BAILIAN_API_KEY: $BAILIAN_API_KEY"
echo "DEEPSEEK_API_KEY: $DEEPSEEK_API_KEY"
echo "=============================================="
echo ""

# 运行视频生成脚本
python generate_video.py $argv
