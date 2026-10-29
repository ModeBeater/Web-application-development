"""
Seed one demo lecture so a fresh `docker compose up` has something to show.

Runs once (migrations are recorded in the django_migrations table) and can be
rolled back with `migrate qa 0001`.
"""

from django.db import migrations

DEMO_CODE = "KBTU26"

DEMO_QUESTIONS = [
    # (text, author, voters)
    ("Do I need to know Dart well before starting with Flutter?", "Aigerim", ["seed-1", "seed-2"]),
    ("Can I build iOS apps with Flutter on Windows?", "", ["seed-1"]),
    ("Which IDE should I use: VS Code or Android Studio?", "Daniyar", []),
]


def create_demo_lecture(apps, schema_editor):
    Lecture = apps.get_model("qa", "Lecture")
    Question = apps.get_model("qa", "Question")
    Upvote = apps.get_model("qa", "Upvote")

    if Lecture.objects.filter(code=DEMO_CODE).exists():
        return
    lecture = Lecture.objects.create(title="Flutter 1 · Lecture 00 · Course introduction", code=DEMO_CODE)
    for text, author, voters in DEMO_QUESTIONS:
        question = Question.objects.create(lecture=lecture, text=text, author=author)
        for voter in voters:
            Upvote.objects.create(question=question, voter_id=voter)


def delete_demo_lecture(apps, schema_editor):
    Lecture = apps.get_model("qa", "Lecture")
    Lecture.objects.filter(code=DEMO_CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("qa", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_demo_lecture, delete_demo_lecture),
    ]
