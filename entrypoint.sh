#!/bin/bash

# Read API config from config.json
CONFIG_FILE="/app/config.json"

if [ -f "$CONFIG_FILE" ]; then
    # Use python to parse JSON (more reliable than jq since container has python)
    ANTHROPIC_API_KEY=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('anthropic_api_key', ''))")
    ANTHROPIC_BASE_URL=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('anthropic_base_url', 'https://api.anthropic.com'))")
    MINI_APP_ENABLED=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('mini_app_api_enabled', True))")
fi

# Create Claude config directory and file
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

# Copy skills to Claude config directory (shared by all users)
if [ -d "/app/.claude/skills" ]; then
    cp -r /app/.claude/skills ~/.claude/
    echo "Skills loaded from /app/.claude/skills"
fi

# Start nginx if Mini App is enabled and nginx is installed
if [ "$MINI_APP_ENABLED" = "True" ] && command -v nginx &> /dev/null; then
    echo "Starting nginx for Mini App..."
    nginx
    echo "Nginx started on port 80"
fi

# Start Bot
exec python3 main.py
