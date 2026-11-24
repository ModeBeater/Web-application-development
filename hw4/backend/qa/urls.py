from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import SimpleRouter

from . import api

app_name = "qa"

# The backend is API-only: the pages are the separate React frontend (../frontend),
# which calls these endpoints with the JWT it holds.
#
# The router turns each ViewSet into URL patterns:
#   lectures  -> /api/lectures/, /api/lectures/{key}/, /api/lectures/{key}/toggle/, /api/lectures/{key}/questions/ ...
#   topics    -> /api/topics/, /api/topics/{id}/
#   questions -> /api/questions/, /api/questions/{id}/, /api/questions/{id}/upvote/, /api/questions/{id}/answer/ ...
router = SimpleRouter()
router.register("lectures", api.LectureViewSet, basename="lecture")
router.register("topics", api.TopicViewSet, basename="topic")
router.register("questions", api.QuestionViewSet, basename="question")

urlpatterns = [
    # API documentation: OpenAPI 3 schema generated from the code, rendered by Swagger UI
    path("docs/", SpectacularSwaggerView.as_view(url_name="qa:schema"), name="docs"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("openapi.yaml", SpectacularAPIView.as_view(), name="openapi"),
    # Service
    path("health/", api.health, name="health"),
    path("api/stats/", api.stats, name="stats"),
    # REST API
    path("api/", api.api_root, name="api-root"),
    path("api/", include(router.urls)),
]
