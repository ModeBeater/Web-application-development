from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class WantedCriminal(models.Model):
    """A wanted criminal from the bounty database."""

    name = models.CharField(max_length=120, null=True, blank=True, help_text="Real name; null when unknown")
    nickname = models.CharField(max_length=120, help_text="Criminal alias")
    reward = models.DecimalField(max_digits=14, decimal_places=2, help_text="Bounty amount")
    # Last known coordinates (optional) + free-text note
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_note = models.TextField(blank=True, default="")
    difficulty = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(10)], help_text="1 (easy) to 10 (deadly)")
    armed = models.BooleanField(default=False)
    has_crew = models.BooleanField(default=False)
    escape_master = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.nickname} ({self.reward})"


class HuntLog(models.Model):
    """One bounty-hunting attempt on a criminal (journal entry)."""

    criminal = models.ForeignKey(WantedCriminal, on_delete=models.CASCADE, related_name="hunts")
    success = models.BooleanField(default=False, help_text="Whether the criminal was captured")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)  # set by the server, never by the client

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"Hunt #{self.pk} on {self.criminal_id}: {'captured' if self.success else 'escaped'}"
