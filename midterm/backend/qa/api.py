"""
JSON REST API.

Two resources, both with full CRUD:

    Lectures   GET /api/lectures/            list        POST /api/lectures/             create
               GET /api/lectures/{id}/       retrieve    PUT/PATCH /api/lectures/{id}/   update
               DELETE /api/lectures/{id}/    delete      POST /api/lectures/{id}/toggle/ open/close
    Questions  GET /api/questions/           list        POST /api/lectures/{id}/questions/ create
               GET /api/questions/{id}/      retrieve    PUT/PATCH /api/questions/{id}/  update
               DELETE /api/questions/{id}/   delete      POST /api/questions/{id}/upvote/, .../answered/

A lecture can be addressed by its numeric id ("12") or by its 6-letter join
code ("K7PX2M"); questions only by id. All bodies and responses are JSON.
The endpoints are stateless (no session login), so they are exempt from CSRF
checks; access control comes with authentication in a later assignment.

Status codes: 200 OK, 201 Created, 204 No Content (delete), 400 bad input,
404 unknown id, 405 wrong method, 409 lecture closed, 503 database down.
"""

import functools
import json

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Exists, OuterRef
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import Lecture, Question, Upvote
from .tunnel import tunnel_public_url
from .voters import get_voter, remember_voter

API_VERSION = "1.0"
MAX_TITLE = 120
MAX_TEXT = 500
MAX_AUTHOR = 40
MAX_LIMIT = 500


# ---------------------------------------------------------------------------
# Helpers: errors, parsing and validation
# ---------------------------------------------------------------------------


class BadRequest(Exception):
    """Raised by helpers for a 400 response with a message."""


def error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def json_errors(view):
    """Turn validation errors (400) and missing objects (404) into JSON responses."""

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except BadRequest as exc:
            return error(str(exc), status=400)
        except Http404 as exc:
            return error(str(exc) or "Not found.", status=404)

    return wrapper


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
    value = data.get(field)
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise BadRequest(f"'{field}' must be a string.")
    value = " ".join(value.split())  # trim and collapse whitespace
    if required and not value:
        raise BadRequest(f"'{field}' is required.")
    if len(value) > max_length:
        raise BadRequest(f"'{field}' must be at most {max_length} characters.")
    return value


def clean_bool(data: dict, field: str, default: bool | None = None) -> bool | None:
    """Read a JSON boolean; `default` is returned when the field is absent."""
    if field not in data:
        return default
    value = data[field]
    if not isinstance(value, bool):
        raise BadRequest(f"'{field}' must be true or false.")
    return value


def query_bool(request, name: str) -> bool | None:
    """Read ?name=true|false from the query string (absent = None)."""
    raw = request.GET.get(name, "").strip().lower()
    if not raw:
        return None
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise BadRequest(f"'{name}' must be true or false.")


def query_int(request, name: str, default: int | None, minimum: int, maximum: int) -> int | None:
    """Read an integer query parameter within [minimum, maximum]."""
    raw = request.GET.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise BadRequest(f"'{name}' must be an integer.") from exc
    if value < minimum or value > maximum:
        raise BadRequest(f"'{name}' must be between {minimum} and {maximum}.")
    return value


def find_lecture(key: str) -> Lecture:
    """Look a lecture up by numeric id ("12") or by join code ("k7px2m" works too)."""
    if key.isdigit() and len(key) <= 9:
        lecture = Lecture.objects.filter(pk=int(key)).first()
        if lecture is not None:
            return lecture
    lecture = Lecture.objects.filter(code=key.upper()).first()
    if lecture is None:
        raise Http404(f"No lecture with id or code '{key}'.")
    return lecture


# ---------------------------------------------------------------------------
# Helpers: URLs and payloads
# ---------------------------------------------------------------------------


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


def iso(moment) -> str:
    """Timestamps in the project time zone (TIME_ZONE in settings), e.g. 2026-10-28T23:34:33+05:00."""
    return timezone.localtime(moment).isoformat(timespec="seconds")


def question_payload(question: Question) -> dict:
    return {
        "id": question.id,
        "lecture_id": question.lecture_id,
        "lecture_code": question.lecture.code,
        "text": question.text,
        "author": question.author or "Anonymous",
        "votes": getattr(question, "votes", 0),
        "voted": bool(getattr(question, "voted", False)),
        "is_answered": question.is_answered,
        "created_at": iso(question.created_at),
    }


def with_votes(queryset, voter_id: str | None = None):
    """Annotate questions with their vote count and whether this voter has voted."""
    queryset = queryset.select_related("lecture").annotate(votes=Count("upvotes", distinct=True))
    if voter_id is not None:
        my_vote = Upvote.objects.filter(question=OuterRef("pk"), voter_id=voter_id)
        queryset = queryset.annotate(voted=Exists(my_vote))
    return queryset


def questions_for(lecture: Lecture, voter_id: str | None = None):
    """Questions of a lecture: most wanted first, answered ones at the bottom."""
    return with_votes(lecture.questions.all(), voter_id).order_by("is_answered", "-votes", "created_at")


def lecture_payload(request, lecture: Lecture, voter_id: str | None = None, with_questions: bool = False) -> dict:
    question_count = getattr(lecture, "question_count", None)
    if question_count is None:
        question_count = lecture.questions.count()
    data = {
        "id": lecture.id,
        "title": lecture.title,
        "code": lecture.code,
        "is_open": lecture.is_open,
        "question_count": question_count,
        "created_at": iso(lecture.created_at),
        "join_url": join_url(request, lecture),
        "screen_url": request.build_absolute_uri(f"/l/{lecture.code}/screen/"),
    }
    if with_questions:
        data["questions"] = [question_payload(q) for q in questions_for(lecture, voter_id)]
    return data


# ---------------------------------------------------------------------------
# Service endpoints
# ---------------------------------------------------------------------------


@require_GET
def api_root(request):
    """Entry point: version and where to find things."""
    return JsonResponse(
        {
            "name": f"{settings.APP_NAME} API",
            "version": API_VERSION,
            "docs": request.build_absolute_uri("/docs/"),
            "openapi": request.build_absolute_uri("/openapi.yaml"),
            "resources": {
                "lectures": request.build_absolute_uri("/api/lectures/"),
                "questions": request.build_absolute_uri("/api/questions/"),
            },
        }
    )


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


# ---------------------------------------------------------------------------
# Lectures
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["GET", "POST"])
@json_errors
def lectures(request):
    """GET: list lectures (?q=, ?is_open=). POST: create a lecture."""
    if request.method == "GET":
        items = Lecture.objects.annotate(question_count=Count("questions"))
        search = request.GET.get("q", "").strip()
        if search:
            items = items.filter(title__icontains=search)
        is_open = query_bool(request, "is_open")
        if is_open is not None:
            items = items.filter(is_open=is_open)
        return JsonResponse({"count": items.count(), "lectures": [lecture_payload(request, item) for item in items]})

    data = parse_body(request)
    title = clean_text(data, "title", MAX_TITLE)
    is_open = clean_bool(data, "is_open", default=True)

    # The join code is random; on the (very rare) collision just draw again.
    for _ in range(5):
        try:
            with transaction.atomic():
                lecture = Lecture.objects.create(title=title, is_open=is_open)
            break
        except IntegrityError:
            continue
    else:
        return error("Could not allocate a join code, please retry.", status=500)

    return JsonResponse(lecture_payload(request, lecture), status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
@json_errors
def lecture_detail(request, key: str):
    """GET: one lecture with its questions. PUT/PATCH: update title/is_open. DELETE: remove it."""
    lecture = find_lecture(key)

    if request.method == "GET":
        voter_id, is_new = get_voter(request)
        response = JsonResponse(lecture_payload(request, lecture, voter_id, with_questions=True))
        return remember_voter(response, voter_id, is_new)

    if request.method == "DELETE":
        lecture.delete()  # its questions and upvotes go with it (on_delete=CASCADE)
        return HttpResponse(status=204)

    # PUT replaces the whole resource (title required); PATCH changes only the given fields.
    partial = request.method == "PATCH"
    data = parse_body(request)
    if partial and not (data.keys() & {"title", "is_open"}):
        raise BadRequest("Provide at least one of: title, is_open.")
    if "title" in data or not partial:
        lecture.title = clean_text(data, "title", MAX_TITLE)
    is_open = clean_bool(data, "is_open", default=None if partial else True)
    if is_open is not None:
        lecture.is_open = is_open
    lecture.save(update_fields=["title", "is_open"])
    return JsonResponse(lecture_payload(request, lecture))


@csrf_exempt
@require_POST
@json_errors
def toggle_open(request, key: str):
    """Open or close a lecture for new questions (lecturer action)."""
    lecture = find_lecture(key)
    lecture.is_open = not lecture.is_open
    lecture.save(update_fields=["is_open"])
    return JsonResponse({"id": lecture.id, "code": lecture.code, "is_open": lecture.is_open})


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["GET", "POST"])
@json_errors
def lecture_questions(request, key: str):
    """GET: questions of one lecture (ordered by votes). POST: ask a new question."""
    lecture = find_lecture(key)

    if request.method == "GET":
        voter_id, is_new = get_voter(request)
        items = [question_payload(q) for q in questions_for(lecture, voter_id)]
        response = JsonResponse({"count": len(items), "questions": items})
        return remember_voter(response, voter_id, is_new)

    if not lecture.is_open:
        return error("This lecture is closed for new questions.", status=409)
    data = parse_body(request)
    text = clean_text(data, "text", MAX_TEXT)
    author = clean_text(data, "author", MAX_AUTHOR, required=False)

    question = Question.objects.create(lecture=lecture, text=text, author=author)
    voter_id, is_new = get_voter(request, data)
    response = JsonResponse(question_payload(question), status=201)
    return remember_voter(response, voter_id, is_new)


@require_GET
@json_errors
def questions(request):
    """All questions, newest first. Filters: ?lecture=<id|code> ?answered= ?q= ?limit= ?offset=."""
    items = with_votes(Question.objects.all()).order_by("-created_at", "-id")
    lecture_key = request.GET.get("lecture", "").strip()
    if lecture_key:
        items = items.filter(lecture=find_lecture(lecture_key))
    answered = query_bool(request, "answered")
    if answered is not None:
        items = items.filter(is_answered=answered)
    search = request.GET.get("q", "").strip()
    if search:
        items = items.filter(text__icontains=search)

    total = items.count()
    limit = query_int(request, "limit", default=None, minimum=1, maximum=MAX_LIMIT)
    offset = query_int(request, "offset", default=0, minimum=0, maximum=10**9)
    items = items[offset : offset + limit] if limit is not None else items[offset:]
    return JsonResponse(
        {
            "count": total,
            "limit": limit,
            "offset": offset,
            "questions": [question_payload(q) for q in items],
        }
    )


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
@json_errors
def question_detail(request, question_id: int):
    """GET: one question. PUT/PATCH: edit text/author/is_answered. DELETE: remove it."""
    question = get_object_or_404(with_votes(Question.objects.all()), pk=question_id)

    if request.method == "GET":
        return JsonResponse(question_payload(question))

    if request.method == "DELETE":
        question.delete()
        return HttpResponse(status=204)

    # PUT replaces the whole resource (text required); PATCH changes only the given fields.
    partial = request.method == "PATCH"
    data = parse_body(request)
    if partial and not (data.keys() & {"text", "author", "is_answered"}):
        raise BadRequest("Provide at least one of: text, author, is_answered.")
    if "text" in data or not partial:
        question.text = clean_text(data, "text", MAX_TEXT)
    if "author" in data or not partial:
        question.author = clean_text(data, "author", MAX_AUTHOR, required=False)
    is_answered = clean_bool(data, "is_answered", default=None if partial else False)
    if is_answered is not None:
        question.is_answered = is_answered
    question.save(update_fields=["text", "author", "is_answered"])
    return JsonResponse(question_payload(question))


@csrf_exempt
@require_POST
@json_errors
def upvote(request, question_id: int):
    """Toggle the caller's upvote on a question."""
    question = get_object_or_404(Question, pk=question_id)
    data = parse_body(request)
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
@json_errors
def answered(request, question_id: int):
    """Mark a question as answered (or reopen it)."""
    question = get_object_or_404(Question, pk=question_id)
    question.is_answered = not question.is_answered
    question.save(update_fields=["is_answered"])
    return JsonResponse({"id": question.id, "is_answered": question.is_answered})
