# Build-time argument: lets us switch the Python version without editing the file
#   docker build --build-arg PYTHON_VERSION=3.12 -t hw1-web .
ARG PYTHON_VERSION=3.13

# Small official base image with a pinned version (no "latest")
FROM python:${PYTHON_VERSION}-slim

# Python behaviour inside a container:
#   PYTHONDONTWRITEBYTECODE - do not write .pyc files into the image
#   PYTHONUNBUFFERED        - send logs straight to stdout so `docker logs` shows them
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# All following instructions (and the running app) work from /app
WORKDIR /app

# Dedicated non-root user: the app must not run as root inside the container
RUN useradd --create-home --uid 1000 appuser

# Dependencies first: this layer is rebuilt only when requirements.txt changes,
# so a code-only change reuses the cached `pip install` layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application source code (filtered by .dockerignore)
COPY --chown=appuser:appuser . .

# Application defaults. Override at run time with `-e NAME=value` or `--env-file`.
# Placed after `pip install` so that changing a default does not invalidate
# the cached dependency layer.
ENV APP_GREETING="Hello from Docker!" \
    APP_ENV=production \
    DJANGO_DEBUG=0

USER appuser

# Documents the port the app listens on; publishing is done with `docker run -p`
EXPOSE 8000

# Docker marks the container healthy/unhealthy based on the /health/ endpoint
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/')"

# Default process (exec form: gunicorn is PID 1 and receives stop signals).
# 0.0.0.0 makes the server reachable from outside the container.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "config.wsgi:application"]
