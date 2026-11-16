"""
Query-string filters for the list endpoints (django-filter).

    GET /api/lectures/?is_open=true&owner=me
    GET /api/questions/?lecture=KBTU26&is_answered=false&author=me&topic=3&has_answer=true&tag_source=auto
    GET /api/topics/?lecture=KBTU26

`?search=` and `?ordering=` come from DRF's SearchFilter / OrderingFilter and are
configured on the viewsets; `?limit=&offset=` from the pagination class.
"""

import django_filters
from rest_framework.exceptions import NotAuthenticated

from .lookup import find_lecture
from .models import Lecture, Question, Topic


def user_or_me(request, value: str):
    """`me` -> the signed-in user, otherwise a user id."""
    if value == "me":
        if not request.user.is_authenticated:
            raise NotAuthenticated("Sign in to use ?owner=me / ?author=me.")
        return request.user.id
    return value


class LectureFilter(django_filters.FilterSet):
    is_open = django_filters.BooleanFilter(help_text="Only open (true) or only closed (false) lectures")
    owner = django_filters.CharFilter(method="filter_owner", help_text="Owner user id, or `me`")

    class Meta:
        model = Lecture
        fields = ["is_open", "owner"]

    def filter_owner(self, queryset, name, value):
        return queryset.filter(owner_id=user_or_me(self.request, value))


class QuestionFilter(django_filters.FilterSet):
    lecture = django_filters.CharFilter(method="filter_lecture", help_text="Lecture id or join code")
    topic = django_filters.NumberFilter(field_name="topic_id", help_text="Only questions tagged with this topic id")
    is_answered = django_filters.BooleanFilter(help_text="Only answered (true) or only open (false) questions")
    has_answer = django_filters.BooleanFilter(
        field_name="answer", lookup_expr="isnull", exclude=True,
        help_text="true = only questions with a written answer, false = without one",
    )
    tag_source = django_filters.ChoiceFilter(
        choices=[("manual", "manual"), ("auto", "auto"), ("none", "none")], method="filter_tag_source",
        help_text="How the topic was assigned: manual, auto, or none (untagged)",
    )
    author = django_filters.CharFilter(method="filter_author", help_text="Author user id, or `me`")

    class Meta:
        model = Question
        fields = ["lecture", "topic", "is_answered", "has_answer", "tag_source", "author"]

    def filter_tag_source(self, queryset, name, value):
        return queryset.filter(tag_source="" if value == "none" else value)

    def filter_lecture(self, queryset, name, value):
        return queryset.filter(lecture=find_lecture(Lecture.objects.all(), value))

    def filter_author(self, queryset, name, value):
        return queryset.filter(author_id=user_or_me(self.request, value))


class TopicFilter(django_filters.FilterSet):
    lecture = django_filters.CharFilter(method="filter_lecture", help_text="Lecture id or join code")

    class Meta:
        model = Topic
        fields = ["lecture"]

    def filter_lecture(self, queryset, name, value):
        return queryset.filter(lecture=find_lecture(Lecture.objects.all(), value))
