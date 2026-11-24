"""
Django settings for the Raise Hand backend.

Every value that differs between environments is read from environment
variables (12-factor style). Docker Compose passes them from the .env file,
so the same image runs in development, in the classroom and in tests.
"""

import os
from datetime import timedelta
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
# The key also signs the JWTs (HMAC-SHA256), so it must be at least 32 bytes long.
SECRET_KEY = env_required("DJANGO_SECRET_KEY")
if len(SECRET_KEY.encode()) < 32:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be at least 32 characters (it signs the JWT tokens).")

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

# Name of the service (API title, /health/)
APP_NAME = os.environ.get("APP_NAME", "Raise Hand")

# Address other devices use to reach this machine, e.g. http://192.168.1.5:8000.
# It is encoded into the QR code. Empty = use the tunnel address if the optional
# `tunnel` service is running, otherwise the address of the incoming request.
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").strip().rstrip("/")

# Metrics server of the optional cloudflared `tunnel` service (see compose.yaml);
# GET <url>/quicktunnel returns the public hostname. Empty = never ask.
TUNNEL_METRICS_URL = os.environ.get("TUNNEL_METRICS_URL", "http://tunnel:2000").strip()

# Address of the separate frontend service as the browser sees it (http://localhost:3000 in
# compose.yaml). Used for the links the API hands out (QR code, projector page) when neither
# PUBLIC_URL nor the tunnel is set. Empty = derive it from the incoming request.
FRONTEND_URL = os.environ.get("FRONTEND_URL", "").strip().rstrip("/")

# Browsers only let a page call an API on another origin when the API says so (CORS).
# The React dev server (5173) and the nginx-served build (3000) are listed by default;
# through the nginx proxy the API is same-origin and CORS is not involved at all.
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"
)

# How often the frontend should poll the API for new questions and votes (reported by /health/)
REFRESH_SECONDS = max(1, env_int("REFRESH_SECONDS", 3))

# Password of the demo accounts created by the seed migration / seed_demo (never for real users)
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "Demo12345!")

# ---------------------------------------------------------------------------
# Apps and middleware (only what this project uses)
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",                      # password hashing, validators, AbstractUser
    "django.contrib.staticfiles",               # static files of the admin, the browsable API and Swagger UI
    "corsheaders",                              # Access-Control-Allow-Origin for the React frontend
    "rest_framework",                           # Django REST Framework: serializers, viewsets, pagination
    "rest_framework_simplejwt.token_blacklist", # refresh tokens are stored so logout/rotation can revoke them
    "django_filters",                           # ?lecture=&is_answered= style filtering
    "drf_spectacular",                          # OpenAPI 3 schema generated from the code
    "accounts",                                 # User model with roles, auth endpoints, user management
    "qa",                                       # lectures, questions, upvotes
]

AUTH_USER_MODEL = "accounts.User"

# Rules every new password must pass (register, change password)
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",   # serves collected static files from gunicorn
    "corsheaders.middleware.CorsMiddleware",        # must come before CommonMiddleware
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
                "django.template.context_processors.request",   # Swagger UI and the browsable API
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
# Static files: collected by entrypoint.sh into STATIC_ROOT, served by WhiteNoise
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

# --- Automatic topic tagging (qa/tagging.py) ---------------------------------
# tfidf (default): char n-gram TF-IDF + keyword bonus; keywords: keyword rule only
TAGGING_BACKEND = os.environ.get("TAGGING_BACKEND", "tfidf")
# Minimum score for an automatic tag; below it the question stays untagged
TAGGING_THRESHOLD = float(os.environ.get("TAGGING_THRESHOLD", "0.18"))
# Minimum cosine similarity for "someone already asked this"
SIMILAR_THRESHOLD = float(os.environ.get("SIMILAR_THRESHOLD", "0.35"))

REST_FRAMEWORK = {
    # Every request may carry "Authorization: Bearer <access token>"; without it request.user is anonymous.
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    # Reading is public, writing needs a signed-in user; the viewsets add role/ownership rules on top.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticatedOrReadOnly"],
    # JSON for clients, the browsable HTML API when opened in a browser
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    # ?limit=&offset= on every list endpoint; responses carry count/next/previous/results
    "DEFAULT_PAGINATION_CLASS": "qa.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    # ?field=value (django-filter), ?search= and ?ordering=
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Timestamps in the project time zone without microseconds: 2026-10-28T23:34:13+05:00
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%S%:z",
}

# ---------------------------------------------------------------------------
# JWT (djangorestframework-simplejwt)
#   access token  — short-lived, sent as "Authorization: Bearer ..." with every request
#   refresh token — long-lived, exchanged for a new pair at /api/auth/refresh/;
#                   rotated on every use and the old one blacklisted, so a stolen
#                   refresh token stops working as soon as the real client refreshes
# ---------------------------------------------------------------------------

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("JWT_ACCESS_MINUTES", 15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("JWT_REFRESH_DAYS", 7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "TOKEN_OBTAIN_SERIALIZER": "accounts.serializers.LoginSerializer",  # adds role + user to the response
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Raise Hand API",
    "VERSION": "3.0",
    "DESCRIPTION": (
        "Live Q&A for lectures: a lecturer starts a **lecture**, the audience scans a QR code, "
        "asks **questions** and upvotes the ones they also want answered.\n\n"
        "Built with Django REST Framework: serializers validate input, viewsets implement "
        "list / retrieve / create / update / delete, django-filter and DRF filters add "
        "`?is_open=`, `?search=`, `?ordering=`, and every list is paginated with `?limit=&offset=`.\n\n"
        "**Authentication**: JWT. `POST /api/auth/login/` returns an `access` token (15 min) and a `refresh` "
        "token (7 days). Send `Authorization: Bearer <access>`; when it expires, `POST /api/auth/refresh/` "
        "with the refresh token returns a new pair (the old refresh token is revoked). "
        "Reading is public; writing needs a user. **Roles**: `student` asks and upvotes, `lecturer` also "
        "creates and manages own lectures, `admin` manages everything and the users.\n\n"
        "A lecture can be addressed by its numeric id or its 6-character join code."
    ),
    "CONTACT": {"name": "Course repository", "url": "https://github.com/ModeBeater/Web-application-development"},
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/",   # tags come from the segment after /api/: lectures, questions
    "COMPONENT_SPLIT_REQUEST": True,  # separate request/response schemas (read-only fields)
    "ENUM_NAME_OVERRIDES": {
        "RoleEnum": [("student", "Student"), ("lecturer", "Lecturer"), ("admin", "Admin")],
        "RegisterRoleEnum": [("student", "Student"), ("lecturer", "Lecturer")],
    },
    "SWAGGER_UI_DIST": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.33.0",
    "SWAGGER_UI_SETTINGS": {"deepLinking": True, "displayRequestDuration": True, "tryItOutEnabled": True},
    "TAGS": [
        {"name": "auth", "description": "Register, login, refresh, logout, profile"},
        {"name": "users", "description": "User management (admin only)"},
        {"name": "lectures", "description": "A lecture (or any session) that collects questions from the audience"},
        {"name": "questions", "description": "Questions asked by the audience, with upvotes"},
        {"name": "service", "description": "Health check, statistics and API root"},
    ],
}

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Almaty"
USE_I18N = True
USE_TZ = True
