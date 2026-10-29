from django.urls import path

from . import api, views

app_name = "qa"

urlpatterns = [
    # HTML pages
    path("", views.home, name="home"),
    path("l/<str:code>/", views.lecture_page, name="lecture"),
    path("l/<str:code>/screen/", views.screen, name="screen"),
    # API documentation (Swagger UI + the OpenAPI spec it renders)
    path("docs/", views.docs, name="docs"),
    path("openapi.yaml", views.openapi_spec, name="openapi"),
    # Health (used by the Docker HEALTHCHECK)
    path("health/", api.health, name="health"),
    # JSON REST API
    path("api/", api.api_root, name="api-root"),
    # Lectures: list / create / retrieve / update / delete
    path("api/lectures/", api.lectures, name="api-lectures"),
    path("api/lectures/<str:key>/", api.lecture_detail, name="api-lecture"),
    path("api/lectures/<str:key>/toggle/", api.toggle_open, name="api-toggle"),
    # Questions: list / create (inside a lecture) / retrieve / update / delete
    path("api/lectures/<str:key>/questions/", api.lecture_questions, name="api-lecture-questions"),
    path("api/questions/", api.questions, name="api-questions"),
    path("api/questions/<int:question_id>/", api.question_detail, name="api-question"),
    path("api/questions/<int:question_id>/upvote/", api.upvote, name="api-upvote"),
    path("api/questions/<int:question_id>/answered/", api.answered, name="api-answered"),
]
