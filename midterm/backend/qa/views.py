"""HTML pages. They render a shell; data comes from the JSON API via JavaScript."""

import segno
from django.conf import settings
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from .api import API_VERSION, join_url, public_base_url
from .models import Lecture, Question, Upvote

OPENAPI_FILE = settings.BASE_DIR / "openapi.yaml"


def home(request):
    """List of lectures, a form to start a new one, and totals from the database."""
    lectures = Lecture.objects.annotate(question_count=Count("questions"))
    stats = {
        "lectures": Lecture.objects.count(),
        "questions": Question.objects.count(),
        "answered": Question.objects.filter(is_answered=True).count(),
        "upvotes": Upvote.objects.count(),
    }
    return render(request, "qa/home.html", {"lectures": lectures, "stats": stats})


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
    qr_svg = segno.make(url, error="m").svg_inline(scale=6, dark="#111827", light=None, omitsize=True)
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


@require_GET
def docs(request):
    """Interactive API documentation (Swagger UI) rendered from /openapi.yaml."""
    return render(request, "qa/docs.html", {"api_version": API_VERSION})


@require_GET
def openapi_spec(request):
    """
    The OpenAPI 3 description of the API, as a YAML file (also usable in Postman: Import).

    The file lists http://localhost:8000 as the server; here it is replaced with the address
    the spec was requested from, so Swagger's "Try it out" stays on the same origin
    (127.0.0.1, a LAN IP or the Cloudflare tunnel) and is not blocked by CORS.
    """
    spec = OPENAPI_FILE.read_text(encoding="utf-8")
    spec = spec.replace("http://localhost:8000", request.build_absolute_uri("/").rstrip("/"))
    return HttpResponse(spec, content_type="application/yaml; charset=utf-8")
