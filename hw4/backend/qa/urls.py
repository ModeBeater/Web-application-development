from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import SimpleRouter

from . import api, views

app_name = "qa"

# The router turns each ViewSet into URL patterns:
#   lectures  -> /api/lectures/, /api/lectures/{key}/, /api/lectures/{key}/toggle/, /api/lectures/{key}/questions/
#   questions -> /api/questions/, /api/questions/{id}/, /api/questions/{id}/upvote/, /api/questions/{id}/answered/
router = SimpleRouter()
router.register("lectures", api.LectureViewSet, basename="lecture")
router.register("questions", api.QuestionViewSet, basename="question")

urlpatterns = [
    # HTML pages (shells; the data comes from the API with the JWT the browser holds)
    path("", views.home, name="home"),
    path("login/", views.login_page, name="login"),
    path("register/", views.register_page, name="register"),
    path("me/", views.cabinet, name="cabinet"),
    path("users/", views.users_page, name="users"),
    path("l/<str:code>/", views.lecture_page, name="lecture"),
    path("l/<str:code>/screen/", views.screen, name="screen"),
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
