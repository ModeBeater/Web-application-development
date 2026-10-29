"""Shared query helpers used by the viewsets, the filters and the HTML pages."""

from django.db.models import Count, Exists, OuterRef, QuerySet
from rest_framework.exceptions import NotFound

from .models import Lecture, Question, Upvote


def find_lecture(queryset: QuerySet, key: str) -> Lecture:
    """Look a lecture up by numeric id ("12") or by join code ("k7px2m" works too)."""
    if key.isdigit() and len(key) <= 9:
        lecture = queryset.filter(pk=int(key)).first()
        if lecture is not None:
            return lecture
    lecture = queryset.filter(code=key.upper()).first()
    if lecture is None:
        raise NotFound(f"No lecture with id or code '{key}'.")
    return lecture


def with_votes(queryset: QuerySet, voter_id: str | None = None) -> QuerySet:
    """Annotate questions with their vote count and whether this voter has voted."""
    queryset = queryset.select_related("lecture").annotate(votes=Count("upvotes", distinct=True))
    if voter_id is not None:
        my_vote = Upvote.objects.filter(question=OuterRef("pk"), voter_id=voter_id)
        queryset = queryset.annotate(voted=Exists(my_vote))
    return queryset


def questions_for(lecture: Lecture, voter_id: str | None = None) -> QuerySet:
    """Questions of a lecture in screen order: most wanted first, answered ones at the bottom."""
    return with_votes(Question.objects.filter(lecture=lecture), voter_id).order_by("is_answered", "-votes", "created_at")
