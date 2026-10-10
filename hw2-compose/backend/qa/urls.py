from django.urls import path

from . import api, views

app_name = "qa"

urlpatterns = [
    # HTML pages
    path("", views.home, name="home"),
    path("l/<str:code>/", views.lecture_page, name="lecture"),
    path("l/<str:code>/screen/", views.screen, name="screen"),
    # Health (used by the Docker HEALTHCHECK)
    path("health/", api.health, name="health"),
    # JSON API
    path("api/lectures/", api.lectures, name="api-lectures"),
    path("api/lectures/<str:code>/", api.lecture_detail, name="api-lecture"),
    path("api/lectures/<str:code>/questions/", api.ask, name="api-ask"),
    path("api/lectures/<str:code>/toggle/", api.toggle_open, name="api-toggle"),
    path("api/questions/<int:question_id>/upvote/", api.upvote, name="api-upvote"),
    path("api/questions/<int:question_id>/answered/", api.answered, name="api-answered"),
]
