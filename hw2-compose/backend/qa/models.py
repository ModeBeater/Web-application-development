import secrets

from django.db import models

# Join codes avoid characters that are easy to confuse when read from a screen (0/O, 1/I).
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6


def generate_code() -> str:
    """Short, human-typable join code such as 'K7PX2M'."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


class Lecture(models.Model):
    """A lecture (or any session) that collects questions from the audience."""

    title = models.CharField(max_length=120)
    code = models.CharField(max_length=CODE_LENGTH, unique=True, default=generate_code, editable=False)
    is_open = models.BooleanField(default=True, help_text="Closed lectures accept no new questions.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} [{self.code}]"


class Question(models.Model):
    """A question asked by someone in the audience."""

    lecture = models.ForeignKey(Lecture, on_delete=models.CASCADE, related_name="questions")
    text = models.CharField(max_length=500)
    author = models.CharField(max_length=40, blank=True, default="", help_text="Empty = anonymous")
    is_answered = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return self.text[:60]


class Upvote(models.Model):
    """One 'me too' per voter per question. The voter is identified by a browser cookie."""

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="upvotes")
    voter_id = models.CharField(max_length=36)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["question", "voter_id"], name="one_upvote_per_voter"),
        ]

    def __str__(self) -> str:
        return f"{self.voter_id[:8]} -> question {self.question_id}"
