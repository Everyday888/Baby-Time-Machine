#!/bin/sh
set -e

echo "[entrypoint] Waiting for MySQL to be ready..."
until python - << 'PY'
import os, sys
import pymysql
try:
    pymysql.connect(
        host=os.getenv("MYSQL_HOST", "db"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
    ).close()
except Exception as e:
    sys.exit(1)
PY
do
    echo "[entrypoint] MySQL not ready yet, retrying in 2s..."
    sleep 2
done
echo "[entrypoint] MySQL is ready."

echo "[entrypoint] Initializing database schema..."
flask init-db

echo "[entrypoint] Starting gunicorn..."
exec gunicorn \
    --workers 2 \
    --bind 0.0.0.0:5000 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    app:app
