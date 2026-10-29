"""Absolute URLs the audience uses (QR code, projector page)."""

from django.conf import settings

from .models import Lecture
from .tunnel import tunnel_public_url


def public_base_url(request) -> tuple[str, str]:
    """
    Where the audience should connect, and where that address came from:
    ("env", PUBLIC_URL) > ("tunnel", running cloudflared) > ("request", the address being used now).
    """
    if settings.PUBLIC_URL:
        return "env", settings.PUBLIC_URL
    tunnel = tunnel_public_url()
    if tunnel:
        return "tunnel", tunnel
    return "request", request.build_absolute_uri("/").rstrip("/")


def join_url(request, lecture: Lecture) -> str:
    """Absolute URL students open (encoded into the QR code)."""
    _, base = public_base_url(request)
    return f"{base}/l/{lecture.code}/"


def screen_url(request, lecture: Lecture) -> str:
    return request.build_absolute_uri(f"/l/{lecture.code}/screen/")
