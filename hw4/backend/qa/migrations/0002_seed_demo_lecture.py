"""
Seed the demo accounts and one demo lecture so a fresh `docker compose up` has something
to sign in with and something to show.

    admin     / DEMO_PASSWORD   role admin     (user management)
    lecturer  / DEMO_PASSWORD   role lecturer  (owns the demo lectures)
    aigerim, daniyar, student / DEMO_PASSWORD   role student

DEMO_PASSWORD comes from .env (default "Demo12345!"). Runs once (migrations are
recorded in django_migrations) and can be rolled back with `migrate qa 0001`.
"""

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations

DEMO_CODE = "KBTU26"

DEMO_USERS = [
    # username, role, first name, last name
    ("admin", "admin", "Site", "Admin"),
    ("lecturer", "lecturer", "Nurkhan", "Tashimov"),
    ("aigerim", "student", "Aigerim", "S."),
    ("daniyar", "student", "Daniyar", "K."),
    ("student", "student", "Demo", "Student"),
]

DEMO_QUESTIONS = [
    # (text, author username, upvoter usernames)
    ("Do I need to know Dart well before starting with Flutter?", "aigerim", ["daniyar", "student"]),
    ("Can I build iOS apps with Flutter on Windows?", "student", ["aigerim"]),
    ("Which IDE should I use: VS Code or Android Studio?", "daniyar", []),
]


def create_demo_data(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Lecture = apps.get_model("qa", "Lecture")
    Question = apps.get_model("qa", "Question")
    Upvote = apps.get_model("qa", "Upvote")

    password = make_password(settings.DEMO_PASSWORD)
    users = {}
    for username, role, first_name, last_name in DEMO_USERS:
        users[username], _ = User.objects.get_or_create(
            username=username,
            defaults={
                "role": role,
                "first_name": first_name,
                "last_name": last_name,
                "email": f"{username}@example.com",
                "password": password,
                "is_staff": role == "admin",
                "is_superuser": role == "admin",
            },
        )

    if Lecture.objects.filter(code=DEMO_CODE).exists():
        return
    lecture = Lecture.objects.create(
        title="Flutter 1 · Lecture 00 · Course introduction", code=DEMO_CODE, owner=users["lecturer"]
    )
    for text, author, voters in DEMO_QUESTIONS:
        question = Question.objects.create(lecture=lecture, text=text, author=users[author])
        for voter in voters:
            Upvote.objects.create(question=question, user=users[voter])


def delete_demo_data(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Lecture = apps.get_model("qa", "Lecture")
    Lecture.objects.filter(code=DEMO_CODE).delete()
    User.objects.filter(username__in=[u[0] for u in DEMO_USERS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("qa", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_demo_data, delete_demo_data),
    ]
