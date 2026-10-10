"""
JSON API.

All writes go through these endpoints; the HTML pages only render shells and
call the API from JavaScript. The endpoints are stateless (no session login),
so they are exempt from CSRF checks; access control comes with authentication
in a later homework.
"""

import json

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Exists, OuterRef
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import Lecture, Question, Upvote
from .tunnel import tunnel_public_url
from .voters import get_voter, remember_voter

MAX_TITLE = 120
MAX_TEXT = 500
MAX_AUTHOR = 40


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class BadRequest(Exception):
    """Raised by helpers for a 400 response with a message."""


def parse_body(request) -> dict:
    """Decode a JSON object from the request body (empty body = {})."""
    if not request.body:
        return {}
    try:
        data = json.loads(request.body)
    except ValueError as exc:
        raise BadRequest("Body must be valid JSON.") from exc
    if not isinstance(data, dict):
        raise BadRequest("Body must be a JSON object.")
    return data


def clean_text(data: dict, field: str, max_length: int, required: bool = True) -> str:
    value = data.get(field, "")
    if not isinstance(value, str):
        raise BadRequest(f"'{field}' must be a string.")
    value = " ".join(value.split())  # trim and collapse whitespace
    if required and not value:
        raise BadRequest(f"'{field}' is required.")
    if len(value) > max_length:
        raise BadRequest(f"'{field}' must be at most {max_length} characters.")
    return value


def error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


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


def question_payload(question: Question) -> dict:
    return {
        "id": question.id,
        "text": question.text,
        "author": question.author or "Anonymous",
        "votes": getattr(question, "votes", 0),
        "voted": bool(getattr(question, "voted", False)),
        "is_answered": question.is_answered,
        "created_at": question.created_at.isoformat(timespec="seconds"),
    }


def questions_for(lecture: Lecture, voter_id: str):
    """Questions with vote counts, most wanted first, answered ones at the bottom."""
    my_vote = Upvote.objects.filter(question=OuterRef("pk"), voter_id=voter_id)
    return (
        lecture.questions.annotate(votes=Count("upvotes"), voted=Exists(my_vote))
        .order_by("is_answered", "-votes", "created_at")
    )


def lecture_payload(request, lecture: Lecture, voter_id: str | None = None) -> dict:
    data = {
        "id": lecture.id,
        "title": lecture.title,
        "code": lecture.code,
        "is_open": lecture.is_open,
        "created_at": lecture.created_at.isoformat(timespec="seconds"),
        "join_url": join_url(request, lecture),
        "screen_url": request.build_absolute_uri(f"/l/{lecture.code}/screen/"),
    }
    if voter_id is not None:
        data["questions"] = [question_payload(q) for q in questions_for(lecture, voter_id)]
    return data


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@require_GET
def health(request):
    """Liveness + database check. Used by the Docker HEALTHCHECK."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0].split(" on ")[0]
    except Exception as exc:  # noqa: BLE001 - any DB failure means unhealthy
        return JsonResponse({"status": "error", "database": str(exc)}, status=503)
    return JsonResponse({"status": "ok", "database": version})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def lectures(request):
    """GET: list lectures with question counts. POST: create a lecture."""
    if request.method == "GET":
        items = Lecture.objects.annotate(question_count=Count("questions"))
        return JsonResponse(
            {
                "lectures": [
                    {**lecture_payload(request, item), "question_count": item.question_count}
                    for item in items
                ]
            }
        )

    try:
        data = parse_body(request)
        title = clean_text(data, "title", MAX_TITLE)
    except BadRequest as exc:
        return error(str(exc))

    # The join code is random; on the (very rare) collision just draw again.
    for _ in range(5):
        try:
            with transaction.atomic():
                lecture = Lecture.objects.create(title=title)
            break
        except IntegrityError:
            continue
    else:
        return error("Could not allocate a join code, please retry.", status=500)

    return JsonResponse(lecture_payload(request, lecture), status=201)


@require_GET
def lecture_detail(request, code: str):
    """A lecture with all its questions, ordered by votes. Polled by the pages."""
    lecture = get_object_or_404(Lecture, code=code.upper())
    voter_id, is_new = get_voter(request)
    response = JsonResponse(lecture_payload(request, lecture, voter_id))
    return remember_voter(response, voter_id, is_new)


@csrf_exempt
@require_POST
def toggle_open(request, code: str):
    """Open or close a lecture for new questions (lecturer action)."""
    lecture = get_object_or_404(Lecture, code=code.upper())
    lecture.is_open = not lecture.is_open
    lecture.save(update_fields=["is_open"])
    return JsonResponse({"code": lecture.code, "is_open": lecture.is_open})


@csrf_exempt
@require_POST
def ask(request, code: str):
    """Create a question in a lecture."""
    lecture = get_object_or_404(Lecture, code=code.upper())
    if not lecture.is_open:
        return error("This lecture is closed for new questions.", status=409)
    try:
        data = parse_body(request)
        text = clean_text(data, "text", MAX_TEXT)
        author = clean_text(data, "author", MAX_AUTHOR, required=False)
    except BadRequest as exc:
        return error(str(exc))

    question = Question.objects.create(lecture=lecture, text=text, author=author)
    voter_id, is_new = get_voter(request, data)
    response = JsonResponse(question_payload(question), status=201)
    return remember_voter(response, voter_id, is_new)


@csrf_exempt
@require_POST
def upvote(request, question_id: int):
    """Toggle the caller's upvote on a question."""
    question = get_object_or_404(Question, pk=question_id)
    try:
        data = parse_body(request)
    except BadRequest as exc:
        return error(str(exc))
    voter_id, is_new = get_voter(request, data)

    deleted, _ = Upvote.objects.filter(question=question, voter_id=voter_id).delete()
    if deleted:
        voted = False
    else:
        try:
            with transaction.atomic():
                Upvote.objects.create(question=question, voter_id=voter_id)
        except IntegrityError:  # two taps at once: the first one already won
            pass
        voted = True

    votes = Upvote.objects.filter(question=question).count()
    response = JsonResponse({"id": question.id, "votes": votes, "voted": voted})
    return remember_voter(response, voter_id, is_new)


@csrf_exempt
@require_POST
def answered(request, question_id: int):
    """Mark a question as answered (or reopen it)."""
    question = get_object_or_404(Question, pk=question_id)
    question.is_answered = not question.is_answered
    question.save(update_fields=["is_answered"])
    return JsonResponse({"id": question.id, "is_answered": question.is_answered})
