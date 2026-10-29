"""
HTML pages. Each view renders a shell template; the data comes from the REST API,
called from the browser with the JWT it holds (static/qa/app.js). Only the
projector page needs the database here, to draw the QR code.
"""

import segno
from django.shortcuts import get_object_or_404, render

from .links import join_url, public_base_url
from .models import Lecture


def home(request):
    return render(request, "qa/home.html")


def login_page(request):
    return render(request, "qa/login.html")


def register_page(request):
    return render(request, "qa/register.html")


def cabinet(request):
    return render(request, "qa/cabinet.html")


def users_page(request):
    return render(request, "qa/users.html")


def lecture_page(request, code: str):
    """Audience page: ask a question, upvote others."""
    lecture = get_object_or_404(Lecture, code=code.upper())
    return render(request, "qa/lecture.html", {"lecture": lecture})


def screen(request, code: str):
    """Projector page: QR code to join plus the live question board."""
    lecture = get_object_or_404(Lecture, code=code.upper())
    source, _ = public_base_url(request)
    url = join_url(request, lecture)
    # omitsize=True -> the SVG gets a viewBox instead of fixed width/height, so CSS can scale
    # it to the panel; without it the drawing keeps its pixel size and gets clipped.
    qr_svg = segno.make(url, error="m").svg_inline(scale=6, dark="#0f172a", light=None, omitsize=True)
    return render(
        request,
        "qa/screen.html",
        {
            "lecture": lecture,
            "join_url": url,
            "qr_svg": qr_svg,
            "join_source": source,  # "env" | "tunnel" | "request"
            "local_only": source == "request" and request.get_host().split(":")[0] in ("localhost", "127.0.0.1"),
        },
    )
