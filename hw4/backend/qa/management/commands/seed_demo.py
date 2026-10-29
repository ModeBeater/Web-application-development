"""
`manage.py seed_demo` — fill the database with realistic demo data:
40 student accounts, 8 lectures of a Flutter course owned by the demo lecturer,
100+ questions with authors and timestamps, a few hundred upvotes, part of the
questions marked as answered.

Demo accounts (password = DEMO_PASSWORD from .env, default "Demo12345!"):
admin (admin), lecturer (lecturer), student / aigerim / daniyar and
student01..student40 (students).

Idempotent: the demo lectures have fixed join codes, so running the command
again does nothing until you pass --clear. The data is generated with a fixed
random seed, so every machine gets the same numbers (handy for a defense).

    docker compose exec web python manage.py seed_demo
    docker compose exec web python manage.py seed_demo --clear   # regenerate
"""

import random
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from qa.models import Lecture, Question, Upvote

User = get_user_model()

# (code, title, days ago, is_open) — codes are fixed so the command can find its own data
DEMO_LECTURES = [
    ("FLT101", "Flutter 1 · Lecture 01 · Dart basics", 14, False),
    ("FLT102", "Flutter 1 · Lecture 02 · Widgets and layout", 12, False),
    ("FLT103", "Flutter 1 · Lecture 03 · State management", 10, False),
    ("FLT104", "Flutter 1 · Lecture 04 · Navigation and routing", 7, False),
    ("FLT105", "Flutter 1 · Lecture 05 · Networking and JSON", 5, False),
    ("FLT106", "Flutter 1 · Lecture 06 · Local storage and persistence", 3, False),
    ("FLT107", "Flutter 1 · Lecture 07 · Animations and custom painting", 1, True),
    ("FLT108", "Flutter 1 · Lecture 08 · Testing, CI and release", 0, True),
]

DEMO_QUESTIONS = {
    "FLT101": [
        "What is the difference between final and const in Dart?",
        "When should I use late instead of a nullable type?",
        "Why does Dart have num, int and double at the same time?",
        "How do named parameters differ from positional ones?",
        "What does the ?. operator return if the object is null?",
        "Is there a way to make a class fully immutable in Dart?",
        "What is the difference between List.of and List.from?",
        "How do extension methods work under the hood?",
        "Why is dynamic discouraged in application code?",
        "What happens if I forget await on a Future?",
        "How do I convert a JSON string into a Dart object without a library?",
        "What is the difference between == and identical()?",
        "Can a Dart enum have methods and fields?",
    ],
    "FLT102": [
        "Why does Column throw 'unbounded height' inside a ListView?",
        "What is the difference between Expanded and Flexible?",
        "When should I use SizedBox instead of Padding?",
        "How does MediaQuery help with different screen sizes?",
        "What is a Key and when do I actually need one?",
        "Why is BuildContext passed everywhere?",
        "How do I center a widget both vertically and horizontally?",
        "What is the difference between Container and DecoratedBox?",
        "How does the widget tree differ from the element tree?",
        "Why do I get 'RenderFlex overflowed by 42 pixels'?",
        "How do Stack and Positioned work together?",
        "Can I nest a ListView inside a SingleChildScrollView?",
        "What does const in front of a widget constructor give me?",
    ],
    "FLT103": [
        "When is setState enough and when do I need a package?",
        "How do StatelessWidget and StatefulWidget differ in lifecycle?",
        "How does InheritedWidget propagate data down the tree?",
        "Provider or Riverpod — which one should a beginner pick?",
        "What is a ChangeNotifier and when does it rebuild the UI?",
        "Why is calling setState after dispose an error?",
        "How do I keep state when navigating back to a screen?",
        "What is the difference between ValueNotifier and StreamController?",
        "How does BLoC separate events from states?",
        "Where should business logic live in a small app?",
        "Does context.watch rebuild the whole widget?",
        "How do I share state between two tabs?",
        "What does 'lifting state up' mean in practice?",
    ],
    "FLT104": [
        "What is the difference between Navigator.push and named routes?",
        "How do I pass arguments to a named route?",
        "How do I return a value from a screen with Navigator.pop?",
        "When should I use go_router instead of Navigator 1.0?",
        "How do deep links work with go_router?",
        "Why does Navigator.of(context) throw inside MaterialApp's builder?",
        "How do I show a dialog and wait for its result?",
        "What is the difference between pushReplacement and pushAndRemoveUntil?",
        "How do nested navigators work with a bottom navigation bar?",
        "How do I protect routes behind authentication?",
        "Can I customize the transition animation between two screens?",
        "What happens to the state of a screen when it is popped?",
        "How do I handle the Android back button?",
    ],
    "FLT105": [
        "http package or dio — what is the real difference?",
        "How do I parse a list of JSON objects into Dart models?",
        "Is json_serializable worth the code generation step?",
        "How do I show a loading indicator while a request is running?",
        "How should I handle a 401 response globally?",
        "Why does FutureBuilder refetch on every rebuild?",
        "How do I cancel a request when the user leaves the screen?",
        "Where should I store the API base URL for dev and prod?",
        "How do I upload a file with multipart/form-data?",
        "How do I add a timeout to a request?",
        "What is the difference between async* and async?",
        "How do I retry a failed request with exponential backoff?",
        "Is it safe to store a JWT in SharedPreferences?",
    ],
    "FLT106": [
        "What is the difference between SharedPreferences and a real database?",
        "When should I pick sqflite, Drift or Hive?",
        "Where does Flutter store app files on iOS versus Android?",
        "Is flutter_secure_storage safe enough for auth tokens?",
        "How do I migrate the database schema when the app updates?",
        "Does SharedPreferences write to disk synchronously?",
        "How do I cache API responses for offline use?",
        "What is Isar and why is it so fast?",
        "How do I store a list of objects in SharedPreferences?",
        "Can two isolates access the same database file?",
        "How do I clear all app data on logout?",
        "What is the path_provider package for?",
        "How big can a Hive box get before it slows down?",
    ],
    "FLT107": [
        "What is the difference between implicit and explicit animations?",
        "When do I need an AnimationController and a TickerProvider?",
        "How does Hero find the matching widget on the next screen?",
        "Why does AnimatedContainer not animate on the first build?",
        "How do I animate a list item being removed?",
        "What does CustomPainter cost when it repaints on every frame?",
        "How do I keep animations at 60 fps on low-end Android phones?",
        "What is the difference between a Tween and a Curve?",
        "How do I pause an animation when the app goes to the background?",
        "Can I use Lottie or Rive instead of hand-written animations?",
        "Why do I get 'Ticker was still active' on dispose?",
        "How does RepaintBoundary help performance?",
        "How do I chain several animations one after another?",
    ],
    "FLT108": [
        "What is the difference between unit, widget and integration tests?",
        "How do I mock an HTTP client in a widget test?",
        "Why does pumpAndSettle hang forever with a CircularProgressIndicator?",
        "How do I find a widget by key instead of by text?",
        "How do I run the tests on every push in GitLab CI?",
        "What does flutter build appbundle produce and why not an APK?",
        "How do I sign an Android release without committing the keystore?",
        "How do I upload a build to TestFlight from the terminal?",
        "What are flavors and how do I set up dev and prod?",
        "How do I hide API keys from the compiled app?",
        "What is golden testing?",
        "How do I measure code coverage for Flutter tests?",
        "What is Shorebird code push and do the stores allow it?",
    ],
}

FIRST_NAMES = [
    "Aigerim", "Daniyar", "Aruzhan", "Alikhan", "Dana", "Nursultan", "Madina", "Yerlan",
    "Kamila", "Arman", "Dias", "Zhanel", "Aidana", "Timur", "Saule", "Bekzat",
    "Inkar", "Rustam", "Assel", "Sanzhar", "Aliya", "Nurlan", "Ayaulym", "Erbol",
    "Dinara", "Askar", "Gulnara", "Bauyrzhan", "Zhanna", "Olzhas", "Tomiris", "Adil",
    "Laura", "Miras", "Aizhan", "Ruslan", "Botagoz", "Galym", "Karina", "Yerzhan",
]
ANSWERED_SHARE = 0.4            # share of questions in closed lectures marked as answered
STUDENTS = 40                   # demo student accounts: student01..student40
VOTE_COUNTS = [0, 1, 2, 3, 5, 8, 13]
VOTE_WEIGHTS = [22, 24, 18, 14, 10, 7, 5]
LECTURE_MINUTES = 90            # questions arrive within the lecture slot


class Command(BaseCommand):
    help = "Create 40 student accounts and 8 demo lectures with 100+ questions, upvotes and timestamps."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Delete previously generated demo data first")
        parser.add_argument("--seed", type=int, default=2026, help="Random seed (default 2026)")

    def demo_users(self) -> tuple[User, list[User]]:
        """The demo lecturer (created by the seed migration) and 40 student accounts (created here, idempotent)."""
        lecturer = User.objects.get(username="lecturer")
        students = []
        created = 0
        for i in range(1, STUDENTS + 1):
            first = FIRST_NAMES[(i - 1) % len(FIRST_NAMES)]
            student, was_created = User.objects.get_or_create(
                username=f"student{i:02d}",
                defaults={"first_name": first, "last_name": f"{chr(65 + i % 26)}.", "email": f"student{i:02d}@example.com",
                          "role": User.Role.STUDENT},
            )
            if was_created:
                student.set_password(settings.DEMO_PASSWORD)
                student.save(update_fields=["password"])
                created += 1
            students.append(student)
        if created:
            self.stdout.write(f"  created {created} student accounts (student01..student{STUDENTS}, password from DEMO_PASSWORD)")
        return lecturer, students

    @transaction.atomic
    def handle(self, *args, **options):
        codes = [code for code, *_ in DEMO_LECTURES]
        existing = Lecture.objects.filter(code__in=codes)
        if existing.exists():
            if not options["clear"]:
                self.stdout.write(
                    f"Demo data already present ({existing.count()} lectures). Use --clear to regenerate."
                )
                return
            deleted, _ = existing.delete()  # questions and upvotes go with the lecture (CASCADE)
            self.stdout.write(f"Removed previous demo data ({deleted} rows).")

        rng = random.Random(options["seed"])
        now = timezone.now()
        lecturer, students = self.demo_users()
        questions_total = upvotes_total = 0

        for code, title, days_ago, is_open in DEMO_LECTURES:
            # Closed lectures are over; an open one started a few minutes ago and is still running
            window = LECTURE_MINUTES if not is_open else 20
            started = now - timedelta(days=days_ago, minutes=window)
            lecture = Lecture.objects.create(title=title, code=code, is_open=is_open, owner=lecturer)
            Lecture.objects.filter(pk=lecture.pk).update(created_at=started)  # bypass auto_now_add

            questions = []
            for text in DEMO_QUESTIONS[code]:
                answered = (not is_open) and rng.random() < ANSWERED_SHARE
                questions.append(Question(lecture=lecture, text=text, author=rng.choice(students), is_answered=answered))
            Question.objects.bulk_create(questions)

            # Spread the questions over the lecture slot, oldest first
            offsets = sorted(rng.randint(1, window - 1) for _ in questions)
            for question, minutes in zip(questions, offsets):
                question.created_at = started + timedelta(minutes=minutes, seconds=rng.randint(0, 59))
            Question.objects.bulk_update(questions, ["created_at"])

            upvotes = []
            for question in questions:
                votes = rng.choices(VOTE_COUNTS, VOTE_WEIGHTS)[0]
                for voter in rng.sample(students, votes):  # sample = unique user per question
                    upvotes.append(Upvote(question=question, user=voter))
            Upvote.objects.bulk_create(upvotes)

            questions_total += len(questions)
            upvotes_total += len(upvotes)
            self.stdout.write(f"  {code}  {title}: {len(questions)} questions, {len(upvotes)} upvotes")

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(DEMO_LECTURES)} lectures, {questions_total} questions, "
                f"{upvotes_total} upvotes from {STUDENTS} students."
            )
        )
