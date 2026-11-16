"""
Query-string filters for the list endpoints (django-filter).

    GET /api/lectures/?is_open=true
    GET /api/questions/?lecture=KBTU26&is_answered=false&topic=3&has_answer=true
    GET /api/topics/?lecture=KBTU26

`?search=` and `?ordering=` come from DRF's SearchFilter / OrderingFilter and are
configured on the viewsets; `?limit=&offset=` from the pagination class.
"""

import django_filters

from .lookup import find_lecture
from .models import Lecture, Question, Topic


class LectureFilter(django_filters.FilterSet):
    is_open = django_filters.BooleanFilter(help_text="Only open (true) or only closed (false) lectures")

    class Meta:
        model = Lecture
        fields = ["is_open"]


class QuestionFilter(django_filters.FilterSet):
    lecture = django_filters.CharFilter(method="filter_lecture", help_text="Lecture id or join code")
    topic = django_filters.NumberFilter(field_name="topic_id", help_text="Only questions tagged with this topic id")
    is_answered = django_filters.BooleanFilter(help_text="Only answered (true) or only open (false) questions")
    has_answer = django_filters.BooleanFilter(
        field_name="answer", lookup_expr="isnull", exclude=True,
        help_text="true = only questions with a written answer, false = without one",
    )

    class Meta:
        model = Question
        fields = ["lecture", "topic", "is_answered", "has_answer"]

    def filter_lecture(self, queryset, name, value):
        return queryset.filter(lecture=find_lecture(Lecture.objects.all(), value))


class TopicFilter(django_filters.FilterSet):
    lecture = django_filters.CharFilter(method="filter_lecture", help_text="Lecture id or join code")

    class Meta:
        model = Topic
        fields = ["lecture"]

    def filter_lecture(self, queryset, name, value):
        return queryset.filter(lecture=find_lecture(Lecture.objects.all(), value))
