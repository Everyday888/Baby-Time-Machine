<<<<<<< HEAD
=======
# ── Stage 1: install Node deps (WebAwesome UI components) ──────────────────
FROM node:20-slim AS node-deps
WORKDIR /app
COPY package.json ./
RUN npm install --production

# ── Stage 2: final runtime image ────────────────────────────────────────────
>>>>>>> 869a0f53c3616651baf139fd86324feb74df20db
FROM python:3.11-slim

WORKDIR /app

<<<<<<< HEAD
# Install system dependencies for MySQL client
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir gunicorn

# Copy application code
COPY . .

# Create images directory for uploads
RUN mkdir -p /app/images

# Copy and set up entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["/entrypoint.sh"]
=======
# System deps for Pillow / cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (includes gunicorn)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Node modules from stage 1 (served via /node_modules/ route)
COPY --from=node-deps /app/node_modules ./node_modules

# Application source
COPY . .

# Ensure upload directory exists
RUN mkdir -p /app/images

EXPOSE 5000

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
>>>>>>> 869a0f53c3616651baf139fd86324feb74df20db
