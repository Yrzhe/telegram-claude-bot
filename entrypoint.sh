#!/bin/bash

# 从环境变量创建 Claude 配置
mkdir -p ~/.claude
cat > ~/.claude/settings.json << EOF
{
  "env": {
    "ANTHROPIC_BASE_URL": "${ANTHROPIC_BASE_URL:-https://api.anthropic.com}",
    "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}"
  }
}
EOF

# 复制 skills 到 Claude 配置目录（所有用户共享）
if [ -d "/app/.claude/skills" ]; then
    cp -r /app/.claude/skills ~/.claude/
    echo "Skills loaded from /app/.claude/skills"
fi

# 启动 Bot
exec python3 main.py
