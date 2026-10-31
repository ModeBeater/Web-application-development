# Build-time argument: switch the Python version without editing the file
#   docker compose build --build-arg PYTHON_VERSION=3.12
ARG PYTHON_VERSION=3.13

# Small official base image with a pinned version (no "latest")
FROM python:${PYTHON_VERSION}-slim

# PYTHONDONTWRITEBYTECODE - no .pyc files in the image
# PYTHONUNBUFFERED        - logs go straight to stdout for `docker compose logs`
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dedicated non-root user for the application process
RUN useradd --create-home --uid 1000 appuser

# Dependencies first: this layer is rebuilt only when requirements.txt changes.
# psycopg[binary] ships libpq inside the wheel, so no apt packages are needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application source (filtered by .dockerignore)
COPY --chown=appuser:appuser . .
# /app itself was created by WORKDIR as root; collectstatic (run as appuser) must be able to create staticfiles/ in it
RUN chmod +x entrypoint.sh && mkdir -p staticfiles && chown appuser:appuser /app /app/staticfiles

USER appuser

# Documents the port the app listens on; publishing is done in compose.yaml
EXPOSE 8000

# Healthy = the app answers AND can query the database (see bounty/api.py:health)
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/')"

# ENTRYPOINT applies migrations (waiting for the database), then runs CMD.
# CMD can be replaced per run: `docker compose run --rm web python manage.py test`
ENTRYPOINT ["./entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "config.wsgi:application"]
