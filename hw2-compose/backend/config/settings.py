"""
Django settings for the Raise Hand backend.

Every value that differs between environments is read from environment
variables (12-factor style). Docker Compose passes them from the .env file,
so the same image runs in development, in the classroom and in tests.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_required(name: str) -> str:
    """Read a secret that must come from the environment — there is no default on purpose."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(
            f"{name} is not set. Copy .env.example to .env, fill in the secrets and start with docker compose up."
        )
    return value


def env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean flag ("1", "true", "yes", "on") from the environment."""
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    """Read an integer from the environment, falling back on bad input."""
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def env_list(name: str, default: str = "") -> list[str]:
    """Read a comma-separated list from the environment."""
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Django core
# ---------------------------------------------------------------------------

# Secrets are never written in code: they come from .env (git-ignored) via Compose.
SECRET_KEY = env_required("DJANGO_SECRET_KEY")

# Debug is OFF unless explicitly enabled with DJANGO_DEBUG=1
DEBUG = env_bool("DJANGO_DEBUG", default=False)

# Hosts/IPs the app may be served on. Add your LAN IP (or "*") for a classroom demo.
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1,0.0.0.0,[::1]")

# Behind a tunnel or reverse proxy (the optional cloudflared service, nginx) the browser
# speaks HTTPS to the proxy and the proxy speaks HTTP to gunicorn. The proxy reports the
# original scheme in this header, so absolute URLs — the QR code — come out as https://.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------------------
# Application configuration
# ---------------------------------------------------------------------------

# Name shown in the page header
APP_NAME = os.environ.get("APP_NAME", "Raise Hand")

# Address other devices use to reach this machine, e.g. http://192.168.1.5:8000.
# It is encoded into the QR code. Empty = use the tunnel address if the optional
# `tunnel` service is running, otherwise the address of the incoming request.
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").strip().rstrip("/")

# Metrics server of the optional cloudflared `tunnel` service (see compose.yaml);
# GET <url>/quicktunnel returns the public hostname. Empty = never ask.
TUNNEL_METRICS_URL = os.environ.get("TUNNEL_METRICS_URL", "http://tunnel:2000").strip()

# How often the pages poll the API for new questions and votes
REFRESH_SECONDS = max(1, env_int("REFRESH_SECONDS", 3))

# ---------------------------------------------------------------------------
# Apps and middleware (only what this project uses)
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "qa",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "qa.context_processors.app_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Database: PostgreSQL, the "db" service from compose.yaml.
# POSTGRES_* names are shared with the official postgres image, so one .env
# configures both containers.
# ---------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "raisehand"),
        "USER": os.environ.get("POSTGRES_USER", "raisehand"),
        "PASSWORD": env_required("POSTGRES_PASSWORD"),
        "HOST": os.environ.get("DB_HOST", "db"),          # service name in compose.yaml
        "PORT": os.environ.get("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,          # reuse connections between requests
        "CONN_HEALTH_CHECKS": True,  # drop a connection the database closed (e.g. after restart)
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Almaty"
USE_I18N = True
USE_TZ = True
