#!/bin/sh
set -e

echo "Waiting for MySQL to be ready..."
while ! python -c "
import pymysql, os, time
try:
    conn = pymysql.connect(
        host=os.getenv('MYSQL_HOST', 'mysql'),
        port=int(os.getenv('MYSQL_PORT', '3306')),
        user=os.getenv('MYSQL_USER', 'root'),
        password=os.getenv('MYSQL_PASSWORD', ''),
    )
    conn.close()
    print('MySQL is ready!')
except Exception as e:
    print(f'MySQL not ready: {e}')
    exit(1)
" 2>/dev/null; do
    sleep 2
done

echo "Initializing database..."
python -c "
import database as db
db.init_database_schema()
print('Database initialized successfully.')
"

echo "Starting application..."
exec gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 120 app:app
