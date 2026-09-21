import platform
import socket

import django
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone


def get_app_info() -> dict:
    """Collect runtime facts that show where and how the app is running."""
    return {
        "greeting": settings.APP_GREETING,
        "environment": settings.APP_ENV,
        "debug": settings.DEBUG,
        # Inside a container the hostname is the short container ID.
        "hostname": socket.gethostname(),
        "python_version": platform.python_version(),
        "django_version": django.get_version(),
        "server_time": timezone.now().isoformat(timespec="seconds"),
    }


def index(request):
    """Home page: renders the runtime info as HTML."""
    return render(request, "core/index.html", {"info": get_app_info()})


def info(request):
    """Same runtime info as JSON (handy for curl)."""
    return JsonResponse(get_app_info())


def health(request):
    """Liveness endpoint used by the Docker HEALTHCHECK."""
    return JsonResponse({"status": "ok"})
