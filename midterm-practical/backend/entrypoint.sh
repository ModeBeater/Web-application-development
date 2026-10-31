#!/bin/sh
# 1. wait for PostgreSQL  2. apply migrations (schema + demo data)  3. static files  4. run CMD (gunicorn)
set -e
python manage.py wait_for_db
python manage.py migrate --noinput
python manage.py collectstatic --noinput --clear >/dev/null
echo "Starting: $*"
exec "$@"
