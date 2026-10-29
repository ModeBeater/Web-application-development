"""Root URL configuration: auth + users from the accounts app, everything else from qa."""

from django.urls import include, path

urlpatterns = [
    path("api/", include("accounts.urls")),
    path("", include("qa.urls")),
]
