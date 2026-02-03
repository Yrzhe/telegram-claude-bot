FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including nginx
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ffmpeg \
    nginx \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (for Claude Agent SDK and frontend build)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude CLI (Claude Agent SDK dependency)
RUN npm install -g @anthropic-ai/claude-code

# Copy Python dependencies
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Build frontend (if webapp directory exists)
COPY webapp/package*.json webapp/
RUN cd webapp && npm install

COPY webapp/ webapp/
RUN cd webapp && npm run build

# Copy frontend build to nginx
RUN mkdir -p /var/www/html && cp -r webapp/dist/* /var/www/html/

# Copy nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Copy application code
COPY . .

# Create user data directory
RUN mkdir -p /app/users

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy entry script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose port 80 for nginx
EXPOSE 80

# Start command
CMD ["/entrypoint.sh"]
