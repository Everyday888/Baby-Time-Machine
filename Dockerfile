FROM node:20-slim AS node_deps

WORKDIR /app

# Install frontend dependencies (Web Awesome and related assets)
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for MySQL client
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list 2>/dev/null || true \
    && apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    -r requirements.txt

# Copy application code
COPY . .

# Bring frontend assets from the Node dependency stage
COPY --from=node_deps /app/node_modules ./node_modules

# Create images directory for uploads
RUN mkdir -p /app/images

# Copy and set up entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["/entrypoint.sh"]
