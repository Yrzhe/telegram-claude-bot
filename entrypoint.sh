#!/bin/bash

# 从 config.json 读取 API 配置
CONFIG_FILE="/app/config.json"

if [ -f "$CONFIG_FILE" ]; then
    # 使用 python 解析 JSON（比 jq 更可靠，因为容器已有 python）
    ANTHROPIC_API_KEY=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('anthropic_api_key', ''))")
    ANTHROPIC_BASE_URL=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('anthropic_base_url', 'https://api.anthropic.com'))")
fi

# 创建 Claude 配置目录和文件
mkdir -p ~/.claude
cat > ~/.claude/settings.json << EOF
{
  "env": {
    "ANTHROPIC_BASE_URL": "${ANTHROPIC_BASE_URL:-https://api.anthropic.com}",
    "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}"
  }
}
EOF

echo "Claude API configured: base_url=${ANTHROPIC_BASE_URL}"

# 复制 skills 到 Claude 配置目录（所有用户共享）
if [ -d "/app/.claude/skills" ]; then
    cp -r /app/.claude/skills ~/.claude/
    echo "Skills loaded from /app/.claude/skills"
fi

# 启动 Bot
exec python3 main.py
