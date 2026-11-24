"""
Absolute URLs of the *frontend* that the API hands out (QR code, projector page).

The pages live in the separate `frontend` service, so the API cannot simply use its
own address. Priority:

    PUBLIC_URL (env)  >  running cloudflared tunnel  >  FRONTEND_URL (env)  >  the address of
    the current request (correct when the request came through the frontend's nginx proxy)
"""

from django.conf import settings

from .models import Lecture
from .tunnel import tunnel_public_url


def public_base_url(request) -> tuple[str, str]:
    """(source, base url without trailing slash); source is "env", "tunnel", "frontend" or "request"."""
    if settings.PUBLIC_URL:
        return "env", settings.PUBLIC_URL
    tunnel = tunnel_public_url()
    if tunnel:
        return "tunnel", tunnel
    if settings.FRONTEND_URL:
        return "frontend", settings.FRONTEND_URL
    return "request", request.build_absolute_uri("/").rstrip("/")


def join_url(request, lecture: Lecture) -> str:
    """Address students open (encoded into the QR code)."""
    _, base = public_base_url(request)
    return f"{base}/l/{lecture.code}/"


def screen_url(request, lecture: Lecture) -> str:
    """Projector page of the frontend."""
    _, base = public_base_url(request)
    return f"{base}/l/{lecture.code}/screen/"
