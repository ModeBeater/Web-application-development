"""Root URL configuration: everything is delegated to the qa app."""

from django.urls import include, path

urlpatterns = [
    path("", include("qa.urls")),
]
