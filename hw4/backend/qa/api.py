"""
REST API built with Django REST Framework.

Three resources, each a ViewSet that the router turns into URLs, plus service endpoints:

    LectureViewSet   GET/POST /api/lectures/   GET/PUT/PATCH/DELETE /api/lectures/{key}/
                     POST /api/lectures/{key}/toggle/   GET/POST /api/lectures/{key}/questions/
                     GET/POST /api/lectures/{key}/topics/   GET/POST/DELETE /api/lectures/{key}/material/
                     GET /api/lectures/{key}/similar/?text=   GET /api/lectures/{key}/suggest/?text=
                     POST /api/lectures/{key}/retag/   GET /api/lectures/{key}/summary/   GET /api/lectures/{key}/export/
    TopicViewSet     GET /api/topics/   GET/PUT/PATCH/DELETE /api/topics/{id}/   GET /api/topics/{id}/questions/
    QuestionViewSet  GET /api/questions/   GET/PUT/PATCH/DELETE /api/questions/{id}/
                     POST /api/questions/{id}/upvote/   POST /api/questions/{id}/answered/
                     GET/PUT/DELETE /api/questions/{id}/answer/

Relationships: Lecture 1-* Topic, Lecture 1-1 LectureMaterial, Lecture 1-* Question,
Topic 1-* Question (SET_NULL), Question 1-* Upvote, Question 1-1 Answer.

Reading is public. Writing needs a signed-in user ("Authorization: Bearer <access token>",
see accounts/api.py) and the role/ownership rules in permissions.py. `{key}` is a numeric
id or the 6-character join code. Error responses follow DRF: {"detail": "..."} for
401/403/404/405/409, {"field": ["message"]} for 400.

Topics are assigned to questions either by the person (topic_id in the body -> "manual")
or by the tagging model in tagging.py (-> "auto" with a confidence score).
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.reverse import reverse

from . import tagging
from .export import lecture_markdown
from .filters import LectureFilter, QuestionFilter, TopicFilter
from .links import join_url, public_base_url, screen_url
from .lookup import find_lecture, questions_for, topics_for, with_votes
from .material import MAX_UPLOAD_BYTES, plan_from_text, read_upload
from .models import Answer, Lecture, LectureMaterial, Question, Topic, Upvote
from .permissions import LecturePermission, QuestionPermission, TopicPermission
from .serializers import (
    AnswerSerializer,
    AnsweredResultSerializer,
    ApiRootSerializer,
    HealthSerializer,
    LectureDetailSerializer,
    LectureSerializer,
    JoinInfoSerializer,
    LectureSummarySerializer,
    MaterialSerializer,
    MaterialUploadResultSerializer,
    QuestionSerializer,
    RetagResultSerializer,
    SimilarQuestionSerializer,
    StatsSerializer,
    TagSuggestionSerializer,
    ToggleResultSerializer,
    TopicSerializer,
    UpvoteResultSerializer,
)

API_VERSION = "4.0"

KEY_PARAM = OpenApiParameter(
    "key", str, OpenApiParameter.PATH, description="Lecture id (`12`) or join code (`KBTU26`, case-insensitive)"
)
TEXT_PARAM = OpenApiParameter("text", str, OpenApiParameter.QUERY, required=True, description="The question text being typed")
FORBIDDEN = OpenApiResponse(description="Signed in, but the role or ownership rules forbid it")
UNAUTHORIZED = OpenApiResponse(description="No or invalid access token")


class LectureClosed(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This lecture is closed for new questions."
    default_code = "lecture_closed"


def truthy(value) -> bool:
    return str(value).strip().lower() not in ("0", "false", "no", "off", "")


# ---------------------------------------------------------------------------
# Lectures
# ---------------------------------------------------------------------------


@extend_schema_view(
    list=extend_schema(
        summary="List lectures",
        description="Newest first, each with its owner, number of questions and topics. `?owner=me` for mine.",
        auth=[],
    ),
    create=extend_schema(
        summary="Create a lecture",
        description="Lecturers and admins only. The caller becomes the owner; a random join code is generated.",
        responses={201: LectureSerializer, 401: UNAUTHORIZED, 403: FORBIDDEN},
    ),
    retrieve=extend_schema(
        summary="Get a lecture by id or code",
        description="The lecture with its topic plan and its questions in screen order (most upvoted first, answered last).",
        parameters=[KEY_PARAM],
        auth=[],
    ),
    update=extend_schema(summary="Replace a lecture (PUT)", parameters=[KEY_PARAM], responses={200: LectureSerializer, 403: FORBIDDEN}),
    partial_update=extend_schema(summary="Update part of a lecture (PATCH)", parameters=[KEY_PARAM], responses={200: LectureSerializer, 403: FORBIDDEN}),
    destroy=extend_schema(
        summary="Delete a lecture",
        description="Owner or admin. Its topics, material, questions, upvotes and answers are removed by cascade.",
        parameters=[KEY_PARAM],
        responses={204: None, 403: FORBIDDEN},
    ),
)
class LectureViewSet(viewsets.ModelViewSet):
    """CRUD for lectures. The router maps list/create/retrieve/update/partial_update/destroy to URLs."""

    queryset = (
        Lecture.objects.select_related("owner")
        .annotate(
            question_count=Count("questions", distinct=True),
            topic_count=Count("topics", distinct=True),
            has_material=Exists(LectureMaterial.objects.filter(lecture=OuterRef("pk"))),
        )
    )
    serializer_class = LectureSerializer
    permission_classes = [LecturePermission]
    filterset_class = LectureFilter
    search_fields = ["title", "code", "owner__username", "owner__first_name", "owner__last_name"]
    ordering_fields = ["created_at", "title", "question_count", "topic_count"]
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
        lecture.ordered_topics = topics_for(lecture)
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

    # ----- questions ----------------------------------------------------------------------------

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
        description="Any signed-in user. The caller becomes the author. Send `topic_id` to tag the question yourself "
        "(`tag_source: manual`); leave it out and the tagging model suggests a topic (`tag_source: auto`, with "
        "`tag_score`) or leaves the question untagged. 409 if the lecture is closed.",
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
        context = {**self.get_serializer_context(), "lecture": lecture}  # topic_id must belong to this lecture
        serializer = QuestionSerializer(data=request.data, context=context)
        serializer.is_valid(raise_exception=True)
        manual = "topic" in serializer.validated_data and serializer.validated_data["topic"] is not None
        question = serializer.save(
            lecture=lecture, author=request.user,
            tag_source=Question.TagSource.MANUAL if manual else Question.TagSource.NONE,
        )
        if not manual:
            tagging.tag_question(question)  # may leave it untagged
        question = with_votes(Question.objects.filter(pk=question.pk), request.user).get()
        return Response(QuestionSerializer(question, context=context).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Similar questions (while typing)",
        description="Existing questions of this lecture that look like `text`, best first — shown to a student before "
        "they post a duplicate. Char n-gram TF-IDF cosine similarity above `SIMILAR_THRESHOLD`.",
        parameters=[KEY_PARAM, TEXT_PARAM],
        responses=SimilarQuestionSerializer(many=True),
        auth=[],
    )
    @action(detail=True, methods=["get"], filter_backends=[])
    def similar(self, request, key=None):
        lecture = self.get_object()
        text = request.query_params.get("text", "")
        matches = tagging.similar_questions(lecture, text)
        ids = [question.id for question, _ in matches]
        by_id = {q.id: q for q in with_votes(Question.objects.filter(pk__in=ids), request.user)}
        context = self.get_serializer_context()
        return Response(
            [
                {"question": QuestionSerializer(by_id[question.id], context=context).data, "similarity": score}
                for question, score in matches if question.id in by_id
            ]
        )

    @extend_schema(
        summary="Preview the automatic tag",
        description="What topic the tagging model would assign to `text`, with the score for every topic. "
        "Nothing is stored — the frontend shows it next to the question field.",
        parameters=[KEY_PARAM, TEXT_PARAM],
        responses=TagSuggestionSerializer,
        auth=[],
    )
    @action(detail=True, methods=["get"], filter_backends=[])
    def suggest(self, request, key=None):
        lecture = self.get_object()
        text = request.query_params.get("text", "").strip()
        if not text:
            raise ValidationError({"text": ["This query parameter is required."]})
        topics = {topic.id: topic for topic in lecture.topics.all()}
        suggestion = tagging.suggest_topics(lecture, [text], topics.values())[0]
        return Response(
            {
                "topic_id": suggestion.topic.id if suggestion.topic else None,
                "topic_title": suggestion.topic.title if suggestion.topic else None,
                "score": suggestion.score,
                "threshold": float(getattr(settings, "TAGGING_THRESHOLD", 0.18)),
                "scores": [
                    {"topic_id": topic_id, "title": topics[topic_id].title, "score": score}
                    for topic_id, score in suggestion.scores
                ],
            }
        )

    @extend_schema(
        summary="Re-tag the questions of a lecture",
        description="Owner or admin. Runs the tagging model again over the lecture's questions — after the topic plan "
        "changed. Manual tags are kept unless `?include_manual=true`.",
        parameters=[KEY_PARAM, OpenApiParameter("include_manual", bool, OpenApiParameter.QUERY, required=False)],
        request=None,
        responses={200: RetagResultSerializer, 403: FORBIDDEN},
    )
    @action(detail=True, methods=["post"], filter_backends=[])
    def retag(self, request, key=None):
        lecture = self.get_object()
        include_manual = truthy(request.query_params.get("include_manual", request.data.get("include_manual", "")))
        return Response(tagging.retag_lecture(lecture, include_manual=include_manual))

    # ----- topics -------------------------------------------------------------------------------

    @extend_schema(
        methods=["GET"],
        summary="List topics of a lecture",
        description="The lecture plan: topics in order, each with its number of tagged questions.",
        parameters=[KEY_PARAM],
        responses=TopicSerializer(many=True),
        auth=[],
    )
    @extend_schema(
        methods=["POST"],
        summary="Add a topic to a lecture",
        description="Owner or admin. One lecture has many topics (one-to-many); the title is unique within the lecture.",
        parameters=[KEY_PARAM],
        request=TopicSerializer,
        responses={201: TopicSerializer, 401: UNAUTHORIZED, 403: FORBIDDEN},
    )
    @action(detail=True, methods=["get", "post"], serializer_class=TopicSerializer, filter_backends=[])
    def topics(self, request, key=None):
        lecture = self.get_object()
        if request.method == "GET":
            page = self.paginate_queryset(topics_for(lecture))
            return self.get_paginated_response(TopicSerializer(page, many=True).data)

        context = {**self.get_serializer_context(), "lecture": lecture}
        serializer = TopicSerializer(data=request.data, context=context)
        serializer.is_valid(raise_exception=True)
        extra = {}
        if "order" not in serializer.validated_data:  # append to the end of the plan by default
            last = lecture.topics.order_by("-order").values_list("order", flat=True).first()
            extra["order"] = (last or 0) + 1
        topic = serializer.save(lecture=lecture, **extra)
        topic.question_count = 0
        return Response(TopicSerializer(topic, context=context).data, status=status.HTTP_201_CREATED)

    # ----- material (one-to-one) ----------------------------------------------------------------

    @extend_schema(
        methods=["GET"],
        summary="Get the uploaded lecture material",
        parameters=[KEY_PARAM],
        responses={200: MaterialSerializer, 404: OpenApiResponse(description="Nothing uploaded yet")},
        auth=[],
    )
    @extend_schema(
        methods=["POST"],
        summary="Upload the lecture text and build the topic plan",
        description="Owner or admin. Either JSON `{\"title\": \"...\", \"text\": \"...\"}` or multipart with a `file` "
        "(.txt, .md or .pdf, up to 5 MB). Replaces the previous material (one per lecture). Unless `extract=false`, "
        "headings become topics (existing titles are updated, the lecturer's own topics are kept), each topic gets "
        "TF-IDF keywords, and the lecture's questions are re-tagged.",
        parameters=[KEY_PARAM],
        request={"multipart/form-data": MaterialSerializer, "application/json": MaterialSerializer},
        responses={200: MaterialUploadResultSerializer, 201: MaterialUploadResultSerializer, 400: OpenApiResponse(description="Empty or too large"), 403: FORBIDDEN},
    )
    @extend_schema(
        methods=["DELETE"],
        summary="Delete the lecture material",
        description="Owner or admin. The topics built from it stay.",
        parameters=[KEY_PARAM],
        responses={204: None, 403: FORBIDDEN, 404: OpenApiResponse(description="Nothing uploaded")},
    )
    @action(
        detail=True, methods=["get", "post", "delete"], serializer_class=MaterialSerializer, filter_backends=[],
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def material(self, request, key=None):
        lecture = self.get_object()
        existing = LectureMaterial.objects.filter(lecture=lecture).select_related("uploaded_by").first()
        context = self.get_serializer_context()

        if request.method == "GET":
            if existing is None:
                raise NotFound("No material has been uploaded for this lecture.")
            return Response(MaterialSerializer(existing, context=context).data)

        if request.method == "DELETE":
            if existing is None:
                raise NotFound("No material has been uploaded for this lecture.")
            existing.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        upload = request.FILES.get("file")
        pages = None
        if upload is not None:
            if upload.size > MAX_UPLOAD_BYTES:
                raise ValidationError({"file": [f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."]})
            text, pages = read_upload(upload.name, upload.read())
            title = request.data.get("title") or upload.name
        else:
            text = request.data.get("text", "")
            title = request.data.get("title", "")
        serializer = MaterialSerializer(existing, data={"title": title, "text": text}, context=context)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            material = serializer.save(lecture=lecture, uploaded_by=request.user)
            created = updated = 0
            if truthy(request.data.get("extract", "true")):
                next_order = (lecture.topics.order_by("-order").values_list("order", flat=True).first() or 0) + 1
                for section in plan_from_text(material.text, pages):
                    topic = Topic.objects.filter(lecture=lecture, title__iexact=section.title).first()
                    keywords = ", ".join(section.keywords)
                    description = section.body[:4000]
                    if topic is None:  # new topics go to the end of the plan, in the order of the text
                        Topic.objects.create(lecture=lecture, title=section.title, keywords=keywords,
                                             description=description, order=next_order)
                        next_order += 1
                        created += 1
                    else:              # a topic the lecturer already has keeps its place and its own keywords
                        topic.keywords, topic.description = topic.keywords or keywords, description
                        topic.save(update_fields=["keywords", "description"])
                        updated += 1
            retag = tagging.retag_lecture(lecture)

        payload = {
            "material": MaterialSerializer(material, context=context).data,
            "topics_created": created,
            "topics_updated": updated,
            "topics": TopicSerializer(topics_for(lecture), many=True).data,
            "retag": retag,
        }
        return Response(payload, status=status.HTTP_200_OK if existing else status.HTTP_201_CREATED)

    # ----- join info for the projector page -------------------------------------------------------

    @extend_schema(
        summary="Join link and QR code",
        description="What the projector page shows: the address students open (QR code as inline SVG), the join "
        "code and where that address came from — `env` (PUBLIC_URL), `tunnel` (running cloudflared), "
        "`frontend` (FRONTEND_URL) or `request` (the address this request came through). `local_only` warns "
        "that the address only works on this computer (localhost).",
        parameters=[KEY_PARAM],
        responses=JoinInfoSerializer,
        auth=[],
    )
    @action(detail=True, methods=["get"], filter_backends=[])
    def join(self, request, key=None):
        import segno

        lecture = self.get_object()
        source, base = public_base_url(request)
        url = join_url(request, lecture)
        # omitsize=True -> the SVG gets a viewBox instead of fixed width/height, so CSS can scale it
        qr_svg = segno.make(url, error="m").svg_inline(scale=6, dark="#0f172a", light=None, omitsize=True)
        host = base.split("://", 1)[-1].split("/")[0].split(":")[0]
        return Response(
            {
                "code": lecture.code,
                "join_url": url,
                "screen_url": screen_url(request, lecture),
                "source": source,
                "local_only": host in ("localhost", "127.0.0.1"),
                "qr_svg": qr_svg,
            }
        )

    # ----- summary and export -------------------------------------------------------------------

    @extend_schema(
        summary="Lecture summary",
        description="Totals and a per-topic breakdown (questions, answered, upvotes) — what the lecturer looks at "
        "after the lecture. The `topics` list ends with the untagged bucket (`id: null`).",
        parameters=[KEY_PARAM],
        responses=LectureSummarySerializer,
        auth=[],
    )
    @action(detail=True, methods=["get"], filter_backends=[])
    def summary(self, request, key=None):
        lecture = self.get_object()
        return Response(lecture_summary(lecture))

    @extend_schema(
        summary="Export the lecture as Markdown",
        description="Topics, questions (with votes and authors) and written answers as a Markdown document — "
        "to send to the audience after the lecture.",
        parameters=[KEY_PARAM],
        responses={(200, "text/markdown"): OpenApiTypes.STR},
        auth=[],
    )
    @action(detail=True, methods=["get"], filter_backends=[])
    def export(self, request, key=None):
        lecture = self.get_object()
        response = HttpResponse(lecture_markdown(lecture), content_type="text/markdown; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="raise-hand-{lecture.code}.md"'
        return response


def lecture_summary(lecture: Lecture) -> dict:
    questions = lecture.questions.all()
    per_topic = []
    for topic in topics_for(lecture):
        tagged = questions.filter(topic=topic)
        per_topic.append(
            {
                "id": topic.id,
                "title": topic.title,
                "questions": tagged.count(),
                "answered": tagged.filter(is_answered=True).count(),
                "upvotes": Upvote.objects.filter(question__in=tagged).count(),
            }
        )
    untagged = questions.filter(topic__isnull=True)
    per_topic.append(
        {
            "id": None,
            "title": "No topic",
            "questions": untagged.count(),
            "answered": untagged.filter(is_answered=True).count(),
            "upvotes": Upvote.objects.filter(question__in=untagged).count(),
        }
    )
    return {
        "id": lecture.id,
        "code": lecture.code,
        "title": lecture.title,
        "is_open": lecture.is_open,
        "questions": questions.count(),
        "answered": questions.filter(is_answered=True).count(),
        "with_written_answer": questions.filter(answer__isnull=False).count(),
        "upvotes": Upvote.objects.filter(question__lecture=lecture).count(),
        "participants": questions.values("author_id").distinct().count(),
        "tagged_auto": questions.filter(tag_source=Question.TagSource.AUTO).count(),
        "tagged_manual": questions.filter(tag_source=Question.TagSource.MANUAL).count(),
        "untagged": untagged.count(),
        "topics": per_topic,
    }


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------


@extend_schema_view(
    list=extend_schema(
        summary="List all topics",
        description="Topics of every lecture; filter with `?lecture=<id|code>`, page with `?limit=&offset=`.",
        auth=[],
    ),
    retrieve=extend_schema(summary="Get a topic by id", auth=[]),
    update=extend_schema(summary="Replace a topic (PUT)", description="Lecture owner or admin.", responses={200: TopicSerializer, 403: FORBIDDEN}),
    partial_update=extend_schema(summary="Update part of a topic (PATCH)", description="Lecture owner or admin.", responses={200: TopicSerializer, 403: FORBIDDEN}),
    destroy=extend_schema(
        summary="Delete a topic",
        description="Lecture owner or admin. The lecture's questions stay; their `topic_id` becomes null (SET_NULL).",
        responses={204: None, 403: FORBIDDEN},
    ),
)
class TopicViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Read / update / delete topics. They are created inside a lecture: POST /api/lectures/{key}/topics/."""

    queryset = Topic.objects.select_related("lecture", "lecture__owner").annotate(question_count=Count("questions"))
    serializer_class = TopicSerializer
    permission_classes = [TopicPermission]
    filterset_class = TopicFilter
    search_fields = ["title", "keywords"]
    ordering_fields = ["order", "title", "question_count", "created_at"]
    ordering = ["lecture_id", "order", "id"]

    @extend_schema(
        summary="List questions of a topic",
        description="Questions tagged with this topic, in screen order (most upvoted first, answered last). Paginated.",
        responses=QuestionSerializer(many=True),
        auth=[],
    )
    @action(detail=True, methods=["get"], serializer_class=QuestionSerializer, filter_backends=[])
    def questions(self, request, pk=None):
        topic = self.get_object()
        queryset = with_votes(Question.objects.filter(topic=topic), request.user).order_by("is_answered", "-votes", "created_at")
        page = self.paginate_queryset(queryset)
        serializer = QuestionSerializer(page, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data)


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


@extend_schema_view(
    list=extend_schema(
        summary="List all questions",
        description="Every question, newest first. Filter with `?lecture=`, `?topic=`, `?is_answered=`, `?has_answer=`, "
        "`?tag_source=manual|auto|none`, `?author=me`, `?search=`, sort with `?ordering=votes|-votes|created_at`, "
        "page with `?limit=&offset=`.",
        auth=[],
    ),
    retrieve=extend_schema(summary="Get a question by id", auth=[]),
    update=extend_schema(summary="Replace a question (PUT)", description="Author, lecture owner or admin. Changing `topic_id` makes the tag manual.", responses={200: QuestionSerializer, 403: FORBIDDEN}),
    partial_update=extend_schema(summary="Update part of a question (PATCH)", description="Author, lecture owner or admin. Changing `topic_id` makes the tag manual.", responses={200: QuestionSerializer, 403: FORBIDDEN}),
    destroy=extend_schema(summary="Delete a question", description="Author, lecture owner or admin. Its upvotes and answer are removed by cascade.", responses={204: None, 403: FORBIDDEN}),
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

    def perform_update(self, serializer):
        extra = {}
        if "topic" in serializer.validated_data:  # a person chose (or removed) the tag
            topic = serializer.validated_data["topic"]
            extra = {
                "tag_source": Question.TagSource.MANUAL if topic is not None else Question.TagSource.NONE,
                "tag_score": None,
            }
        serializer.save(**extra)

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

    @extend_schema(
        methods=["GET"],
        summary="Get the written answer",
        description="The lecturer's answer to this question (one-to-one). 404 while there is none.",
        responses={200: AnswerSerializer, 404: OpenApiResponse(description="No answer yet")},
        auth=[],
    )
    @extend_schema(
        methods=["PUT"],
        summary="Write or replace the answer",
        description="Lecture owner or admin. Creates the answer (201) or replaces the existing one (200); the caller "
        "becomes its author and the question is marked as answered.",
        request=AnswerSerializer,
        responses={200: AnswerSerializer, 201: AnswerSerializer, 403: FORBIDDEN},
    )
    @extend_schema(
        methods=["DELETE"],
        summary="Delete the answer",
        description="Lecture owner or admin. Removes the written answer and reopens the question.",
        responses={204: None, 403: FORBIDDEN, 404: OpenApiResponse(description="No answer")},
    )
    @action(detail=True, methods=["get", "put", "delete"], serializer_class=AnswerSerializer, filter_backends=[])
    def answer(self, request, pk=None):
        question = self.get_object()
        existing = Answer.objects.filter(question=question).select_related("author").first()
        context = self.get_serializer_context()

        if request.method == "GET":
            if existing is None:
                raise NotFound("This question has no answer yet.")
            return Response(AnswerSerializer(existing, context=context).data)

        if request.method == "DELETE":
            if existing is None:
                raise NotFound("This question has no answer yet.")
            with transaction.atomic():
                existing.delete()
                Question.objects.filter(pk=question.pk).update(is_answered=False)
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = AnswerSerializer(existing, data=request.data, context=context)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            answer = serializer.save(question=question, author=request.user)
            Question.objects.filter(pk=question.pk).update(is_answered=True)
        created = existing is None
        return Response(
            AnswerSerializer(answer, context=context).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


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
    return Response(
        {"status": "ok", "app": settings.APP_NAME, "version": API_VERSION, "database": version,
         "refresh_seconds": settings.REFRESH_SECONDS}
    )


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
            "topics": Topic.objects.count(),
            "questions": Question.objects.count(),
            "answered": Question.objects.filter(is_answered=True).count(),
            "answers": Answer.objects.count(),
            "tagged": Question.objects.filter(topic__isnull=False).count(),
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
            "topics": link("qa:topic-list"),
            "questions": link("qa:question-list"),
            "users": link("accounts:user-list"),
        }
    )
