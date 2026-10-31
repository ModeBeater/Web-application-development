"""?min_reward= ?max_reward= ?armed= ?has_crew= ?escape_master= for criminals; ?criminal_id= for hunts."""

import django_filters
from django import forms
from django_filters.widgets import BooleanWidget

from .models import HuntLog, WantedCriminal


class StrictBooleanWidget(BooleanWidget):
    """Like django-filter's BooleanWidget, but hands unknown values on so they can be rejected."""

    def value_from_datadict(self, data, files, name):
        raw = data.get(name)
        value = super().value_from_datadict(data, files, name)
        if value is None and raw not in (None, ""):
            return raw
        return value


class StrictBooleanField(forms.NullBooleanField):
    widget = StrictBooleanWidget

    def to_python(self, value):
        if value in (None, ""):
            return None
        if value in (True, False):
            return value
        raise forms.ValidationError("Use true or false.", code="invalid")


class StrictBooleanFilter(django_filters.BooleanFilter):
    """`?armed=true` / `?armed=false`; anything else is a 400 instead of being silently ignored."""

    field_class = StrictBooleanField


class WantedCriminalFilter(django_filters.FilterSet):
    min_reward = django_filters.NumberFilter(field_name="reward", lookup_expr="gte", help_text="Minimum bounty")
    max_reward = django_filters.NumberFilter(field_name="reward", lookup_expr="lte", help_text="Maximum bounty")
    armed = StrictBooleanFilter()
    has_crew = StrictBooleanFilter()
    escape_master = StrictBooleanFilter()
    min_difficulty = django_filters.NumberFilter(field_name="difficulty", lookup_expr="gte")
    max_difficulty = django_filters.NumberFilter(field_name="difficulty", lookup_expr="lte")

    class Meta:
        model = WantedCriminal
        fields = ["min_reward", "max_reward", "armed", "has_crew", "escape_master", "min_difficulty", "max_difficulty"]


class HuntLogFilter(django_filters.FilterSet):
    criminal_id = django_filters.NumberFilter(field_name="criminal_id", help_text="Only hunts of this criminal")
    success = StrictBooleanFilter()

    class Meta:
        model = HuntLog
        fields = ["criminal_id", "success"]
