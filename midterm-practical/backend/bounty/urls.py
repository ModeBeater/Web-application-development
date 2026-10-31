from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import api

router = SimpleRouter()
router.register("criminals", api.WantedCriminalViewSet, basename="criminal")
router.register("hunts", api.HuntLogViewSet, basename="hunt")

urlpatterns = [
    path("api/", api.api_root, name="api-root"),
    path("api/", include(router.urls)),
    path("health/", api.health, name="health"),
    path("", api.api_root),
]
