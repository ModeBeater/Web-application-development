#!/bin/sh
# Container entrypoint:
#   1. wait until PostgreSQL accepts connections (clear one-line messages, no tracebacks)
#   2. bring the database schema up to date
#   3. optionally load demo data (SEED_DEMO=1 in .env; the command is idempotent)
#   4. run the command given as CMD (gunicorn by default)
set -e

python manage.py wait_for_db
python manage.py migrate --noinput
python manage.py collectstatic --noinput --clear >/dev/null   # CSS/JS for the browsable API, served by WhiteNoise

case "${SEED_DEMO:-0}" in
    1|true|yes|on) python manage.py seed_demo ;;
esac

echo "Starting: $*"
exec "$@"
