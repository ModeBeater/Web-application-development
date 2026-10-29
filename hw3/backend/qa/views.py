"""HTML pages. They render a shell; data comes from the REST API via JavaScript."""

import segno
from django.db.models import Count
from django.shortcuts import get_object_or_404, render

from .links import join_url, public_base_url
from .models import Lecture, Question, Upvote


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
