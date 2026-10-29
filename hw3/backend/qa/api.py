"""
REST API built with Django REST Framework.

Two resources, each a ViewSet that the router turns into URLs:

    LectureViewSet   GET/POST /api/lectures/   GET/PUT/PATCH/DELETE /api/lectures/{key}/
                     POST /api/lectures/{key}/toggle/   GET/POST /api/lectures/{key}/questions/
    QuestionViewSet  GET /api/questions/   GET/PUT/PATCH/DELETE /api/questions/{id}/
                     POST /api/questions/{id}/upvote/   POST /api/questions/{id}/answered/

Serializers (serializers.py) validate input and shape output; filters.py adds
?lecture=&is_answered=; pagination.py adds ?limit=&offset=. `{key}` is a
numeric id or the 6-character join code. Error responses follow DRF:
{"detail": "..."} for 404/405/409, {"field": ["message"]} for 400.
There is no authentication yet — it is the subject of HW4.
"""

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models import Count
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.reverse import reverse

from .filters import LectureFilter, QuestionFilter
from .lookup import find_lecture, questions_for, with_votes
from .models import Lecture, Question, Upvote
from .serializers import (
    AnsweredResultSerializer,
    ApiRootSerializer,
    HealthSerializer,
    LectureDetailSerializer,
    LectureSerializer,
    QuestionSerializer,
    ToggleResultSerializer,
    UpvoteRequestSerializer,
    UpvoteResultSerializer,
)
from .voters import get_voter, remember_voter

API_VERSION = "2.0"

KEY_PARAM = OpenApiParameter(
    "key", str, OpenApiParameter.PATH, description="Lecture id (`12`) or join code (`KBTU26`, case-insensitive)"
)


class LectureClosed(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This lecture is closed for new questions."
    default_code = "lecture_closed"


# ---------------------------------------------------------------------------
# Lectures
# ---------------------------------------------------------------------------


@extend_schema_view(
    list=extend_schema(summary="List lectures", description="Newest first, each with its number of questions."),
    create=extend_schema(summary="Create a lecture", description="A random 6-character join code is generated."),
    retrieve=extend_schema(
        summary="Get a lecture by id or code",
        description="The lecture with its questions in screen order (most upvoted first, answered last). "
        "Sets the anonymous `voter` cookie so that `voted` flags are per browser.",
        parameters=[KEY_PARAM],
    ),
    update=extend_schema(summary="Replace a lecture (PUT)", parameters=[KEY_PARAM]),
    partial_update=extend_schema(summary="Update part of a lecture (PATCH)", parameters=[KEY_PARAM]),
    destroy=extend_schema(
        summary="Delete a lecture",
        description="Its questions and upvotes are removed by cascade.",
        parameters=[KEY_PARAM],
    ),
)
class LectureViewSet(viewsets.ModelViewSet):
    """CRUD for lectures. The router maps list/create/retrieve/update/partial_update/destroy to URLs."""

    queryset = Lecture.objects.annotate(question_count=Count("questions"))
    serializer_class = LectureSerializer
    filterset_class = LectureFilter
    search_fields = ["title", "code"]
    ordering_fields = ["created_at", "title", "question_count"]
    ordering = ["-created_at"]
    lookup_url_kwarg = "key"        # /api/lectures/{key}/
    lookup_value_regex = r"[^/]+"   # ids and join codes

    def get_serializer_class(self):
        if getattr(self, "action", None) == "retrieve":
            return LectureDetailSerializer
        return LectureSerializer

    def get_object(self) -> Lecture:
        """DRF looks up by pk; here `{key}` may also be a join code."""
        lecture = find_lecture(self.get_queryset(), self.kwargs["key"])
        self.check_object_permissions(self.request, lecture)
        return lecture

    def retrieve(self, request, key=None):
        lecture = self.get_object()
        voter_id, is_new = get_voter(request)
        lecture.ordered_questions = questions_for(lecture, voter_id)
        response = Response(self.get_serializer(lecture).data)
        return remember_voter(response, voter_id, is_new)

    def perform_create(self, serializer):
        # The join code is random; on the (very rare) collision just draw again.
        for _ in range(5):
            try:
                with transaction.atomic():
                    serializer.save()
                return
            except IntegrityError:
                continue
        raise APIException("Could not allocate a join code, please retry.")

    @extend_schema(
        summary="Open / close a lecture",
        description="Flips `is_open`. A closed lecture rejects new questions with 409.",
        parameters=[KEY_PARAM],
        request=None,
        responses=ToggleResultSerializer,
    )
    @action(detail=True, methods=["post"], filter_backends=[])
    def toggle(self, request, key=None):
        lecture = self.get_object()
        lecture.is_open = not lecture.is_open
        lecture.save(update_fields=["is_open"])
        return Response({"id": lecture.id, "code": lecture.code, "is_open": lecture.is_open})

    @extend_schema(
        methods=["GET"],
        summary="List questions of a lecture",
        description="Ordered like the screen: most upvoted first, answered ones last. Paginated.",
        parameters=[KEY_PARAM],
        responses=QuestionSerializer(many=True),
    )
    @extend_schema(
        methods=["POST"],
        summary="Ask a question (create)",
        description="Creates a question in the lecture. 409 if the lecture is closed.",
        parameters=[KEY_PARAM],
        request=QuestionSerializer,
        responses={201: QuestionSerializer},
    )
    @action(detail=True, methods=["get", "post"], serializer_class=QuestionSerializer, filter_backends=[])
    def questions(self, request, key=None):
        lecture = self.get_object()
        if request.method == "GET":
            voter_id, is_new = get_voter(request)
            page = self.paginate_queryset(questions_for(lecture, voter_id))
            serializer = QuestionSerializer(page, many=True, context=self.get_serializer_context())
            return remember_voter(self.get_paginated_response(serializer.data), voter_id, is_new)

        if not lecture.is_open:
            raise LectureClosed()
        serializer = QuestionSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        serializer.save(lecture=lecture)
        voter_id, is_new = get_voter(request, request.data)
        return remember_voter(Response(serializer.data, status=status.HTTP_201_CREATED), voter_id, is_new)


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


@extend_schema_view(
    list=extend_schema(
        summary="List all questions",
        description="Every question in the database, newest first. Filter with `?lecture=`, `?is_answered=`, "
        "`?search=`, sort with `?ordering=votes|-votes|created_at`, page with `?limit=&offset=`.",
    ),
    retrieve=extend_schema(summary="Get a question by id"),
    update=extend_schema(summary="Replace a question (PUT)"),
    partial_update=extend_schema(summary="Update part of a question (PATCH)"),
    destroy=extend_schema(summary="Delete a question", description="Its upvotes are removed by cascade."),
)
class QuestionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Read / update / delete questions. They are created inside a lecture: POST /api/lectures/{key}/questions/."""

    serializer_class = QuestionSerializer
    filterset_class = QuestionFilter
    search_fields = ["text", "author"]
    ordering_fields = ["created_at", "votes", "is_answered"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        voter_id, _ = get_voter(self.request)
        return with_votes(Question.objects.all(), voter_id)

    @extend_schema(
        summary="Toggle an upvote",
        description="Adds the caller's upvote, or removes it if it already exists. The caller is the `voter` "
        "value in the body, else the `voter` cookie (created on first call).",
        request=UpvoteRequestSerializer,
        responses=UpvoteResultSerializer,
    )
    @action(detail=True, methods=["post"], filter_backends=[])
    def upvote(self, request, pk=None):
        question = self.get_object()
        voter_id, is_new = get_voter(request, request.data)

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
        return remember_voter(Response({"id": question.id, "votes": votes, "voted": voted}), voter_id, is_new)

    @extend_schema(
        summary='Toggle "answered"',
        description="Marks the question as answered, or reopens it when it already is.",
        request=None,
        responses=AnsweredResultSerializer,
    )
    @action(detail=True, methods=["post"], filter_backends=[])
    def answered(self, request, pk=None):
        question = self.get_object()
        question.is_answered = not question.is_answered
        question.save(update_fields=["is_answered"])
        return Response({"id": question.id, "is_answered": question.is_answered})


# ---------------------------------------------------------------------------
# Service endpoints
# ---------------------------------------------------------------------------


@extend_schema(
    tags=["service"],
    summary="Health check",
    description="Runs `SELECT version()` on PostgreSQL. Used by the Docker `HEALTHCHECK`.",
    responses={200: HealthSerializer, 503: HealthSerializer},
    operation_id="health",
)
@api_view(["GET"])
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0].split(" on ")[0]
    except Exception as exc:  # noqa: BLE001 - any DB failure means unhealthy
        return Response({"status": "error", "database": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({"status": "ok", "database": version})


@extend_schema(
    tags=["service"],
    summary="API root",
    description="Version number and links to everything.",
    responses=ApiRootSerializer,
    operation_id="api_root",
)
@api_view(["GET"])
def api_root(request, format=None):
    return Response(
        {
            "name": f"{settings.APP_NAME} API",
            "version": API_VERSION,
            "docs": reverse("qa:docs", request=request, format=format),
            "schema": reverse("qa:schema", request=request, format=format),
            "health": reverse("qa:health", request=request, format=format),
            "lectures": reverse("qa:lecture-list", request=request, format=format),
            "questions": reverse("qa:question-list", request=request, format=format),
        }
    )
