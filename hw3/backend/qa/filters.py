"""
Query-string filters for the list endpoints (django-filter).

    GET /api/lectures/?is_open=true
    GET /api/questions/?lecture=KBTU26&is_answered=false

`?search=` and `?ordering=` come from DRF's SearchFilter / OrderingFilter and are
configured on the viewsets; `?limit=&offset=` from the pagination class.
"""

import django_filters

from .lookup import find_lecture
from .models import Lecture, Question


class LectureFilter(django_filters.FilterSet):
    is_open = django_filters.BooleanFilter(help_text="Only open (true) or only closed (false) lectures")

    class Meta:
        model = Lecture
        fields = ["is_open"]


class QuestionFilter(django_filters.FilterSet):
    lecture = django_filters.CharFilter(method="filter_lecture", help_text="Lecture id or join code")
    is_answered = django_filters.BooleanFilter(help_text="Only answered (true) or only open (false) questions")

    class Meta:
        model = Question
        fields = ["lecture", "is_answered"]

    def filter_lecture(self, queryset, name, value):
        return queryset.filter(lecture=find_lecture(Lecture.objects.all(), value))
