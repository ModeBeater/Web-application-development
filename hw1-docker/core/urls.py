from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.index, name="index"),
    path("api/info/", views.info, name="info"),
    path("health/", views.health, name="health"),
]
