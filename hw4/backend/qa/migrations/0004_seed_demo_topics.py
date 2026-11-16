"""
Give the demo lecture KBTU26 (created in 0002) three topics, tag its questions and
answer one of them, so a fresh `docker compose up` shows the new relationships:

    Lecture 1 -- * Topic 1 -- * Question 1 -- 1 Answer

Reversible: `migrate qa 0003` removes the topics (questions keep existing, their
topic becomes NULL) and the answer.
"""

from django.db import migrations

DEMO_CODE = "KBTU26"

DEMO_TOPICS = [
    # (title, keywords, order, question texts that belong to it)
    ("Dart language", "dart, language, syntax, null safety", 1,
     ["Do I need to know Dart well before starting with Flutter?"]),
    ("Tooling and setup", "ide, vs code, android studio, sdk, install", 2,
     ["Which IDE should I use: VS Code or Android Studio?"]),
    ("Platforms", "ios, android, windows, macos, web, build", 3,
     ["Can I build iOS apps with Flutter on Windows?"]),
]

DEMO_ANSWER = (
    "Can I build iOS apps with Flutter on Windows?",
    "You can write and test the code on Windows, but the iOS build itself needs Xcode, "
    "so a Mac (or a CI service with macOS runners) is required for the final build.",
    "lecturer",  # username of the demo lecturer (created in 0002)
)


def seed_topics(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Lecture = apps.get_model("qa", "Lecture")
    Topic = apps.get_model("qa", "Topic")
    Question = apps.get_model("qa", "Question")
    Answer = apps.get_model("qa", "Answer")

    lecture = Lecture.objects.filter(code=DEMO_CODE).first()
    if lecture is None or lecture.topics.exists():
        return
    for title, keywords, order, texts in DEMO_TOPICS:
        topic = Topic.objects.create(lecture=lecture, title=title, keywords=keywords, order=order)
        # tagged "by hand" in the seed; new questions get their tag from the model (qa/tagging.py)
        Question.objects.filter(lecture=lecture, text__in=texts).update(topic=topic, tag_source="manual")

    text, answer, username = DEMO_ANSWER
    question = Question.objects.filter(lecture=lecture, text=text).first()
    if question is not None and not Answer.objects.filter(question=question).exists():
        Answer.objects.create(question=question, text=answer, author=User.objects.filter(username=username).first())
        Question.objects.filter(pk=question.pk).update(is_answered=True)


def unseed_topics(apps, schema_editor):
    Lecture = apps.get_model("qa", "Lecture")
    Topic = apps.get_model("qa", "Topic")
    Answer = apps.get_model("qa", "Answer")
    lecture = Lecture.objects.filter(code=DEMO_CODE).first()
    if lecture is None:
        return
    Answer.objects.filter(question__lecture=lecture).delete()
    Topic.objects.filter(lecture=lecture).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("qa", "0003_topics_material_answers"),
    ]

    operations = [
        migrations.RunPython(seed_topics, unseed_topics),
    ]
