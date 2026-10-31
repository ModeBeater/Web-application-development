"""
REST API.

    GET  /api/criminals/            list (?min_reward= ?max_reward= ?armed= ?has_crew= ?escape_master= ?sort=reward|-reward)
    GET  /api/criminals/{id}/       one criminal
    GET  /api/hunts/                list hunt logs (?criminal_id=)
    POST /api/hunts/                record a capture attempt  {"criminal_id", "success", "notes"}
    GET  /api/hunts/{id}/           one hunt log
    PATCH /api/hunts/{id}/          update success / notes      (PUT also works)
    DELETE /api/hunts/{id}/         delete a hunt log

Errors follow DRF: {"detail": "..."} for 404/405, {"field": ["message"]} for 400.
"""

from django.db import connection
from django.db.models import Count
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse

from .filters import HuntLogFilter, WantedCriminalFilter
from .models import HuntLog, WantedCriminal
from .serializers import HuntLogSerializer, WantedCriminalSerializer


class SortFilter(filters.OrderingFilter):
    """OrderingFilter that reads `?sort=` instead of `?ordering=` (as the assignment specifies)."""

    ordering_param = "sort"


class WantedCriminalViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only: the bounty database is maintained elsewhere; hunters only read it."""

    queryset = WantedCriminal.objects.annotate(hunt_count=Count("hunts"))
    serializer_class = WantedCriminalSerializer
    filterset_class = WantedCriminalFilter
    filter_backends = [DjangoFilterBackend, SortFilter]
    ordering_fields = ["reward", "difficulty", "id", "nickname"]
    ordering = ["id"]


class HuntLogViewSet(viewsets.ModelViewSet):
    """Full CRUD for the bounty-hunting journal."""

    queryset = HuntLog.objects.select_related("criminal")
    serializer_class = HuntLogSerializer
    filterset_class = HuntLogFilter
    filter_backends = [DjangoFilterBackend, SortFilter]
    ordering_fields = ["created_at", "id", "success"]
    ordering = ["-created_at", "-id"]


@api_view(["GET"])
def api_root(request, format=None):
    return Response(
        {
            "name": "Space Bounty Hunters API",
            "criminals": reverse("criminal-list", request=request, format=format),
            "hunts": reverse("hunt-list", request=request, format=format),
            "examples": {
                "filtered_criminals": request.build_absolute_uri("/api/criminals/?min_reward=5000&armed=true&sort=-reward"),
                "hunts_of_criminal": request.build_absolute_uri("/api/hunts/?criminal_id=5"),
            },
        }
    )


@api_view(["GET"])
def health(request):
    """Used by the Docker HEALTHCHECK: 200 when the app can query PostgreSQL, 503 otherwise."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001 - any DB failure means "unhealthy"
        return Response({"status": "error", "database": str(exc)}, status=503)
    return Response({"status": "ok", "database": "ok"})
