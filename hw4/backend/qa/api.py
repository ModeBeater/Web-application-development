"""
REST API built with Django REST Framework.

Two resources, each a ViewSet that the router turns into URLs:

    LectureViewSet   GET/POST /api/lectures/   GET/PUT/PATCH/DELETE /api/lectures/{key}/
                     POST /api/lectures/{key}/toggle/   GET/POST /api/lectures/{key}/questions/
    QuestionViewSet  GET /api/questions/   GET/PUT/PATCH/DELETE /api/questions/{id}/
                     POST /api/questions/{id}/upvote/   POST /api/questions/{id}/answered/

Reading is public. Writing needs a signed-in user ("Authorization: Bearer
<access token>", see accounts/api.py) and the role/ownership rules in
permissions.py. `{key}` is a numeric id or the 6-character join code.
Error responses follow DRF: {"detail": "..."} for 401/403/404/405/409,
{"field": ["message"]} for 400.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.models import Count
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.reverse import reverse

from .filters import LectureFilter, QuestionFilter
from .lookup import find_lecture, questions_for, with_votes
from .models import Lecture, Question, Upvote
from .permissions import LecturePermission, QuestionPermission
from .serializers import (
    AnsweredResultSerializer,
    ApiRootSerializer,
    HealthSerializer,
    LectureDetailSerializer,
    LectureSerializer,
    QuestionSerializer,
    StatsSerializer,
    ToggleResultSerializer,
    UpvoteResultSerializer,
)

API_VERSION = "3.0"

KEY_PARAM = OpenApiParameter(
    "key", str, OpenApiParameter.PATH, description="Lecture id (`12`) or join code (`KBTU26`, case-insensitive)"
)
FORBIDDEN = OpenApiResponse(description="Signed in, but the role or ownership rules forbid it")
UNAUTHORIZED = OpenApiResponse(description="No or invalid access token")


class LectureClosed(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This lecture is closed for new questions."
    default_code = "lecture_closed"


# ---------------------------------------------------------------------------
# Lectures
# ---------------------------------------------------------------------------


@extend_schema_view(
    list=extend_schema(
        summary="List lectures",
        description="Newest first, each with its owner and number of questions. `?owner=me` for mine.",
        auth=[],
    ),
    create=extend_schema(
        summary="Create a lecture",
        description="Lecturers and admins only. The caller becomes the owner; a random join code is generated.",
        responses={201: LectureSerializer, 401: UNAUTHORIZED, 403: FORBIDDEN},
    ),
    retrieve=extend_schema(
        summary="Get a lecture by id or code",
        description="The lecture with its questions in screen order (most upvoted first, answered last).",
        parameters=[KEY_PARAM],
        auth=[],
    ),
    update=extend_schema(summary="Replace a lecture (PUT)", parameters=[KEY_PARAM], responses={200: LectureSerializer, 403: FORBIDDEN}),
    partial_update=extend_schema(summary="Update part of a lecture (PATCH)", parameters=[KEY_PARAM], responses={200: LectureSerializer, 403: FORBIDDEN}),
    destroy=extend_schema(
        summary="Delete a lecture",
        description="Owner or admin. Its questions and upvotes are removed by cascade.",
        parameters=[KEY_PARAM],
        responses={204: None, 403: FORBIDDEN},
    ),
)
class LectureViewSet(viewsets.ModelViewSet):
    """CRUD for lectures. The router maps list/create/retrieve/update/partial_update/destroy to URLs."""

    queryset = Lecture.objects.select_related("owner").annotate(question_count=Count("questions"))
    serializer_class = LectureSerializer
    permission_classes = [LecturePermission]
    filterset_class = LectureFilter
    search_fields = ["title", "code", "owner__username", "owner__first_name", "owner__last_name"]
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
        lecture.ordered_questions = questions_for(lecture, request.user)
        return Response(self.get_serializer(lecture).data)

    def perform_create(self, serializer):
        # The join code is random; on the (very rare) collision just draw again.
        for _ in range(5):
            try:
                with transaction.atomic():
                    serializer.save(owner=self.request.user)
                return
            except IntegrityError:
                continue
        raise APIException("Could not allocate a join code, please retry.")

    @extend_schema(
        summary="Open / close a lecture",
        description="Owner or admin. Flips `is_open`; a closed lecture rejects new questions with 409.",
        parameters=[KEY_PARAM],
        request=None,
        responses={200: ToggleResultSerializer, 403: FORBIDDEN},
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
        auth=[],
    )
    @extend_schema(
        methods=["POST"],
        summary="Ask a question (create)",
        description="Any signed-in user. The caller becomes the author. 409 if the lecture is closed.",
        parameters=[KEY_PARAM],
        request=QuestionSerializer,
        responses={201: QuestionSerializer, 401: UNAUTHORIZED, 409: OpenApiResponse(description="Lecture closed")},
    )
    @action(detail=True, methods=["get", "post"], serializer_class=QuestionSerializer, filter_backends=[])
    def questions(self, request, key=None):
        lecture = self.get_object()
        if request.method == "GET":
            page = self.paginate_queryset(questions_for(lecture, request.user))
            serializer = QuestionSerializer(page, many=True, context=self.get_serializer_context())
            return self.get_paginated_response(serializer.data)

        if not lecture.is_open:
            raise LectureClosed()
        serializer = QuestionSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        serializer.save(lecture=lecture, author=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


@extend_schema_view(
    list=extend_schema(
        summary="List all questions",
        description="Every question, newest first. Filter with `?lecture=`, `?is_answered=`, `?author=me`, "
        "`?search=`, sort with `?ordering=votes|-votes|created_at`, page with `?limit=&offset=`.",
        auth=[],
    ),
    retrieve=extend_schema(summary="Get a question by id", auth=[]),
    update=extend_schema(summary="Replace a question (PUT)", description="Author, lecture owner or admin.", responses={200: QuestionSerializer, 403: FORBIDDEN}),
    partial_update=extend_schema(summary="Update part of a question (PATCH)", description="Author, lecture owner or admin.", responses={200: QuestionSerializer, 403: FORBIDDEN}),
    destroy=extend_schema(summary="Delete a question", description="Author, lecture owner or admin. Its upvotes are removed by cascade.", responses={204: None, 403: FORBIDDEN}),
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
    permission_classes = [QuestionPermission]
    filterset_class = QuestionFilter
    search_fields = ["text", "author__username", "author__first_name", "author__last_name"]
    ordering_fields = ["created_at", "votes", "is_answered"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        return with_votes(Question.objects.all(), self.request.user)

    @extend_schema(
        summary="Toggle an upvote",
        description="Any signed-in user: adds their upvote, or removes it if it already exists.",
        request=None,
        responses={200: UpvoteResultSerializer, 401: UNAUTHORIZED},
    )
    @action(detail=True, methods=["post"], filter_backends=[])
    def upvote(self, request, pk=None):
        question = self.get_object()
        deleted, _ = Upvote.objects.filter(question=question, user=request.user).delete()
        if deleted:
            voted = False
        else:
            try:
                with transaction.atomic():
                    Upvote.objects.create(question=question, user=request.user)
            except IntegrityError:  # two taps at once: the first one already won
                pass
            voted = True
        votes = Upvote.objects.filter(question=question).count()
        return Response({"id": question.id, "votes": votes, "voted": voted})

    @extend_schema(
        summary='Toggle "answered"',
        description="Lecture owner or admin. Marks the question as answered, or reopens it.",
        request=None,
        responses={200: AnsweredResultSerializer, 403: FORBIDDEN},
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
    auth=[],
)
@api_view(["GET"])
@permission_classes([AllowAny])
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
    summary="Statistics",
    description="Totals shown on the home page.",
    responses=StatsSerializer,
    operation_id="stats",
    auth=[],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def stats(request):
    return Response(
        {
            "lectures": Lecture.objects.count(),
            "open_lectures": Lecture.objects.filter(is_open=True).count(),
            "questions": Question.objects.count(),
            "answered": Question.objects.filter(is_answered=True).count(),
            "upvotes": Upvote.objects.count(),
            "users": get_user_model().objects.count(),
        }
    )


@extend_schema(
    tags=["service"],
    summary="API root",
    description="Version number and links to everything.",
    responses=ApiRootSerializer,
    operation_id="api_root",
    auth=[],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def api_root(request, format=None):
    def link(name):
        return reverse(name, request=request, format=format)

    return Response(
        {
            "name": f"{settings.APP_NAME} API",
            "version": API_VERSION,
            "docs": link("qa:docs"),
            "schema": link("qa:schema"),
            "health": link("qa:health"),
            "stats": link("qa:stats"),
            "auth": {
                "register": link("accounts:register"),
                "login": link("accounts:login"),
                "refresh": link("accounts:refresh"),
                "logout": link("accounts:logout"),
                "me": link("accounts:me"),
            },
            "lectures": link("qa:lecture-list"),
            "questions": link("qa:question-list"),
            "users": link("accounts:user-list"),
        }
    )
