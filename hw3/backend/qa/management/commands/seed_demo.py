"""
`manage.py seed_demo` — fill the database with realistic demo data:
8 lectures of a Flutter course, each with 3 topics, 100+ questions with authors,
timestamps and topic tags, a few hundred upvotes from 40 anonymous voters, part of
the questions marked as answered and one written answer per lecture.

Idempotent: the demo lectures have fixed join codes, so running the command
again does nothing until you pass --clear. The data is generated with a fixed
random seed, so every machine gets the same numbers (handy for a defense).

    docker compose exec web python manage.py seed_demo
    docker compose exec web python manage.py seed_demo --clear   # regenerate
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from qa.models import Answer, Lecture, Question, Topic, Upvote

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

# (title, keywords) per lecture — questions are tagged with the topic whose keywords they mention
DEMO_TOPICS = {
    "FLT101": [
        ("Variables and types", "final, const, late, nullable, num, int, double, dynamic, ?."),
        ("Functions and classes", "parameter, named, positional, class, immutable, enum, extension, ==, identical, list."),
        ("Async and JSON", "await, future, json"),
    ],
    "FLT102": [
        ("Layout widgets", "column, row, expanded, flexible, sizedbox, padding, container, decoratedbox, stack, positioned, center, overflow, listview, scroll"),
        ("Widget tree and keys", "key, buildcontext, element tree, const"),
        ("Responsive UI", "mediaquery, screen size"),
    ],
    "FLT103": [
        ("setState and lifecycle", "setstate, stateless, stateful, lifecycle, dispose"),
        ("Provider, Riverpod, BLoC", "provider, riverpod, changenotifier, bloc, context.watch, valuenotifier, stream, inheritedwidget"),
        ("App architecture", "business logic, lifting state, share state, tabs, keep state"),
    ],
    "FLT104": [
        ("Navigator 1.0", "navigator.push, named route, navigator.pop, pushreplacement, dialog, arguments, back button"),
        ("go_router and deep links", "go_router, deep link"),
        ("Nested navigation and guards", "nested, bottom navigation, authentication, transition, state of a screen"),
    ],
    "FLT105": [
        ("HTTP clients", "http package, dio, timeout, retry, cancel, multipart, upload"),
        ("JSON parsing", "parse, json_serializable, dart models"),
        ("Auth, loading and errors", "401, jwt, sharedpreferences, loading, futurebuilder, base url, async*"),
    ],
    "FLT106": [
        ("Key-value storage", "sharedpreferences, secure_storage, list of objects, synchronously"),
        ("Databases", "sqflite, drift, hive, isar, migrate, isolates, box"),
        ("Files and cache", "path_provider, files, cache, offline, clear"),
    ],
    "FLT107": [
        ("Implicit vs explicit", "implicit, explicit, animatedcontainer, tween, curve, chain"),
        ("Controllers and performance", "animationcontroller, tickerprovider, 60 fps, repaintboundary, custompainter, ticker, pause"),
        ("Hero, Lottie and lists", "hero, lottie, rive, list item"),
    ],
    "FLT108": [
        ("Testing", "unit, widget, integration, mock, pumpandsettle, by key, golden, coverage"),
        ("CI/CD", "gitlab ci, every push, testflight, shorebird"),
        ("Build and release", "appbundle, apk, sign, keystore, flavors, api keys"),
    ],
}

# One written answer per lecture (question text -> answer); the rest of the "answered"
# questions were answered orally, which is why is_answered and Answer are separate things.
DEMO_ANSWERS = {
    "What is the difference between final and const in Dart?":
        "final is a run-time constant: assigned once, but the value can be computed. "
        "const is a compile-time constant and the object is canonicalized, so two identical const values are the same instance.",
    "What is the difference between Expanded and Flexible?":
        "Both sit inside a Row/Column. Expanded forces the child to fill the free space (fit: tight); "
        "Flexible lets the child be smaller than the space it is offered (fit: loose).",
    "When is setState enough and when do I need a package?":
        "setState is enough while the state is used by one widget subtree. The moment two distant screens need the same data, "
        "or you want to test logic without widgets, move it to Provider/Riverpod/BLoC.",
    "How do I pass arguments to a named route?":
        "Navigator.pushNamed(context, '/details', arguments: item) and read ModalRoute.of(context)!.settings.arguments on the other side; "
        "with go_router pass them as path or query parameters instead.",
    "How should I handle a 401 response globally?":
        "Add an interceptor (dio) or a wrapper around the client: on 401 try to refresh the token once, retry the request, "
        "and if the refresh fails clear the session and go to the login screen.",
    "When should I pick sqflite, Drift or Hive?":
        "Relational data with queries and joins: Drift (type-safe) or raw sqflite. Simple objects and speed: Hive or Isar. "
        "A few settings: SharedPreferences.",
    "What is the difference between implicit and explicit animations?":
        "Implicit (AnimatedContainer, AnimatedOpacity) animate automatically when a property changes. "
        "Explicit ones give you an AnimationController, so you control start, stop, repeat and curves yourself.",
    "What is the difference between unit, widget and integration tests?":
        "Unit tests check pure Dart logic, widget tests pump a widget tree in memory and interact with it, "
        "integration tests drive the whole app on a device or emulator.",
}
ANSWER_AUTHOR = "Nurkhan Tashimov"

AUTHORS = [
    "Aigerim", "Daniyar", "Aruzhan", "Alikhan", "Dana", "Nursultan", "Madina", "Yerlan",
    "Kamila", "Arman", "Dias", "Zhanel", "Aidana", "Timur", "Saule", "Bekzat",
    "Inkar", "Rustam", "Assel", "Sanzhar", "Aliya", "Nurlan", "Ayaulym", "Erbol",
]
ANONYMOUS_SHARE = 0.35          # share of questions asked without a name
ANSWERED_SHARE = 0.4            # share of questions in closed lectures marked as answered
VOTERS = 40                     # distinct anonymous voters (cookie ids)
VOTE_COUNTS = [0, 1, 2, 3, 5, 8, 13]
VOTE_WEIGHTS = [22, 24, 18, 14, 10, 7, 5]
LECTURE_MINUTES = 90            # questions arrive within the lecture slot


def pick_topic(text: str, topics: list[tuple[Topic, list[str]]]) -> Topic | None:
    """The topic whose keywords appear most often in the question text (None if no keyword matches)."""
    lowered = text.lower()
    best, best_hits = None, 0
    for topic, words in topics:
        hits = sum(1 for word in words if word in lowered)
        if hits > best_hits:
            best, best_hits = topic, hits
    return best


class Command(BaseCommand):
    help = "Create 8 demo lectures with topics, 100+ tagged questions, answers, upvotes and timestamps."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Delete previously generated demo data first")
        parser.add_argument("--seed", type=int, default=2026, help="Random seed (default 2026)")

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
        voters = [f"demo-voter-{i:02d}" for i in range(1, VOTERS + 1)]
        questions_total = upvotes_total = 0

        for code, title, days_ago, is_open in DEMO_LECTURES:
            # Closed lectures are over; an open one started a few minutes ago and is still running
            window = LECTURE_MINUTES if not is_open else 20
            started = now - timedelta(days=days_ago, minutes=window)
            lecture = Lecture.objects.create(title=title, code=code, is_open=is_open)
            Lecture.objects.filter(pk=lecture.pk).update(created_at=started)  # bypass auto_now_add

            topics = []
            for order, (topic_title, keywords) in enumerate(DEMO_TOPICS[code], start=1):
                topic = Topic.objects.create(lecture=lecture, title=topic_title, keywords=keywords, order=order)
                topics.append((topic, [word.strip() for word in keywords.lower().split(",") if word.strip()]))

            questions = []
            for text in DEMO_QUESTIONS[code]:
                author = "" if rng.random() < ANONYMOUS_SHARE else rng.choice(AUTHORS)
                answered = (not is_open) and rng.random() < ANSWERED_SHARE
                if text in DEMO_ANSWERS:
                    answered = True  # a written answer implies the question is answered
                questions.append(
                    Question(lecture=lecture, text=text, author=author, is_answered=answered,
                             topic=pick_topic(text, topics))
                )
            Question.objects.bulk_create(questions)

            answers = [
                Answer(question=question, text=DEMO_ANSWERS[question.text], author=ANSWER_AUTHOR)
                for question in questions if question.text in DEMO_ANSWERS
            ]
            Answer.objects.bulk_create(answers)

            # Spread the questions over the lecture slot, oldest first
            offsets = sorted(rng.randint(1, window - 1) for _ in questions)
            for question, minutes in zip(questions, offsets):
                question.created_at = started + timedelta(minutes=minutes, seconds=rng.randint(0, 59))
            Question.objects.bulk_update(questions, ["created_at"])

            upvotes = []
            for question in questions:
                votes = rng.choices(VOTE_COUNTS, VOTE_WEIGHTS)[0]
                for voter in rng.sample(voters, votes):  # sample = unique voter per question
                    upvotes.append(Upvote(question=question, voter_id=voter))
            Upvote.objects.bulk_create(upvotes)

            questions_total += len(questions)
            upvotes_total += len(upvotes)
            tagged = sum(1 for question in questions if question.topic_id)
            self.stdout.write(
                f"  {code}  {title}: {len(topics)} topics, {len(questions)} questions ({tagged} tagged), "
                f"{len(answers)} answer(s), {len(upvotes)} upvotes"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(DEMO_LECTURES)} lectures with {Topic.objects.filter(lecture__code__in=codes).count()} topics, "
                f"{questions_total} questions, {Answer.objects.filter(question__lecture__code__in=codes).count()} answers, "
                f"{upvotes_total} upvotes from {VOTERS} voters."
            )
        )
