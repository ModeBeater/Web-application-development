import secrets

from django.conf import settings
from django.db import models

# Join codes avoid characters that are easy to confuse when read from a screen (0/O, 1/I).
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6


def generate_code() -> str:
    """Short, human-typable join code such as 'K7PX2M'."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


class Lecture(models.Model):
    """A lecture (or any session) that collects questions from the audience. Owned by a lecturer."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lectures")
    title = models.CharField(max_length=120)
    code = models.CharField(max_length=CODE_LENGTH, unique=True, default=generate_code, editable=False)
    is_open = models.BooleanField(default=True, help_text="Closed lectures accept no new questions.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} [{self.code}]"


class LectureMaterial(models.Model):
    """
    The text of the lecture (slides exported to text, lecture notes, a Markdown outline) —
    at most one per lecture (one-to-one). It is the source for the automatic topic plan:
    headings become topics, the section text feeds the tagging model (see tagging.py).
    """

    lecture = models.OneToOneField(Lecture, on_delete=models.CASCADE, related_name="material")
    title = models.CharField(max_length=200, blank=True, default="", help_text="File name or a short label")
    text = models.TextField(help_text="Plain text of the lecture")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploaded_materials"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Material of {self.lecture.code}: {self.title or len(self.text)} chars"


class Topic(models.Model):
    """
    A sub-topic of a lecture ("Dart basics" -> "null safety", "collections", ...).

    One lecture has many topics (one-to-many); deleting the lecture deletes them. Topics
    come from the lecturer (manually) or from the uploaded material (headings). Questions
    are tagged with a topic — by the student or automatically by the tagging model.
    """

    lecture = models.ForeignKey(Lecture, on_delete=models.CASCADE, related_name="topics")
    title = models.CharField(max_length=120)
    keywords = models.CharField(
        max_length=300, blank=True, default="", help_text="Comma-separated hints, e.g. 'null, late, ?.'"
    )
    description = models.TextField(
        blank=True, default="", help_text="What the topic covers — the section text when extracted from material"
    )
    order = models.PositiveSmallIntegerField(default=0, help_text="Position in the lecture plan")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["lecture", "title"], name="unique_topic_title_per_lecture"),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.lecture.code})"


class Question(models.Model):
    """A question asked by a signed-in member of the audience."""

    class TagSource(models.TextChoices):
        NONE = "", "not tagged"
        MANUAL = "manual", "chosen by a person"
        AUTO = "auto", "suggested by the tagging model"

    lecture = models.ForeignKey(Lecture, on_delete=models.CASCADE, related_name="questions")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="questions")
    # Optional tag. SET_NULL on purpose: a topic is a label, not the owner of the question —
    # removing a topic from the lecture plan must not delete the audience's questions.
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True, related_name="questions")
    tag_source = models.CharField(max_length=6, choices=TagSource.choices, default=TagSource.NONE, blank=True)
    tag_score = models.FloatField(null=True, blank=True, help_text="Similarity 0..1 when the tag was automatic")
    text = models.CharField(max_length=500)
    is_answered = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return self.text[:60]


class Upvote(models.Model):
    """One 'me too' per user per question."""

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="upvotes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="upvotes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["question", "user"], name="one_upvote_per_user"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} -> question {self.question_id}"


class Answer(models.Model):
    """
    The lecturer's written answer to a question — at most one per question (one-to-one).

    Deleting the question deletes its answer (CASCADE). Writing an answer marks the question
    as answered; deleting it reopens the question (see api.py).
    """

    question = models.OneToOneField(Question, on_delete=models.CASCADE, related_name="answer")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="answers"
    )
    text = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Answer to question {self.question_id}"
