from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import api

app_name = "accounts"

router = SimpleRouter()
router.register("users", api.UserViewSet, basename="user")

urlpatterns = [
    path("auth/register/", api.register, name="register"),
    path("auth/login/", api.LoginView.as_view(), name="login"),
    path("auth/refresh/", api.RefreshView.as_view(), name="refresh"),
    path("auth/logout/", api.logout, name="logout"),
    path("auth/me/", api.me, name="me"),
    path("auth/me/password/", api.change_password, name="password"),
    path("", include(router.urls)),
]
