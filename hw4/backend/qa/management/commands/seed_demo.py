"""
`manage.py seed_demo` — fill the database with realistic demo data:
40 student accounts, 10 lectures of a Flutter course owned by the demo lecturer,
each with lecture material and a 3-topic plan (one lecture gets its plan extracted
from the uploaded text), 120+ questions with authors, timestamps and topic tags (most
of them assigned by the tagging model, some chosen "manually"), a few hundred upvotes,
part of the questions marked as answered and one or two written answers per lecture.
Every table ends up with well over 10 rows.

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

from qa import tagging
from qa.material import plan_from_text
from qa.models import Answer, Lecture, LectureMaterial, Question, Topic, Upvote

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
    ("FLT201", "Flutter 2 · Lecture 01 · Firebase: auth, Firestore and push", 6, False),
    ("FLT202", "Flutter 2 · Lecture 02 · Platform channels and native code", 4, False),
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
    "FLT201": [
        "How do I sign in with Google through Firebase Auth on both platforms?",
        "Why does FirebaseAuth.instance.currentUser return null right after app start?",
        "What is the difference between a Firestore collection and a document?",
        "How do I listen to Firestore changes in real time with a StreamBuilder?",
        "How do Firestore security rules work and where do I test them?",
        "Can I query Firestore by two fields without a composite index?",
        "How do I receive push notifications when the app is in the background?",
        "Why do iOS push notifications need an APNs key in the Firebase console?",
        "How do I show a local notification from an FCM data message?",
        "How much does Firestore cost per read and how do I reduce reads?",
        "How do I handle the token refresh for FCM?",
    ],
    "FLT202": [
        "What is a MethodChannel and when do I need one?",
        "How do I call a Kotlin function from Dart and get the result back?",
        "What is the difference between MethodChannel and EventChannel?",
        "How do I write the iOS side of a channel in Swift?",
        "Can I use an existing native SDK without writing a plugin?",
        "What is dart:ffi and when is it better than a platform channel?",
        "How do I create a federated plugin package?",
        "Why does my channel call throw MissingPluginException?",
        "How do I pass a byte array through a channel efficiently?",
        "How do I run native code on a background thread and report progress?",
        "What is a PlatformView and why is it slow?",
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
    "FLT201": [
        ("Firebase Auth", "firebaseauth, google sign-in, currentuser, sign in, app start"),
        ("Firestore", "firestore, collection, document, streambuilder, security rules, composite index, query, reads, cost"),
        ("Push notifications", "push, fcm, apns, notification, background, token refresh, data message"),
    ],
    "FLT202": [
        ("Method and event channels", "methodchannel, eventchannel, kotlin, swift, missingpluginexception, byte array, background thread"),
        ("Plugins and FFI", "plugin, federated, native sdk, dart:ffi, ffi"),
        ("Platform views", "platformview, native view, slow"),
    ],
}

# One or two written answers per lecture (question text -> answer); the rest of the "answered"
# questions were answered orally, which is why is_answered and Answer are separate things.
DEMO_ANSWERS = {
    "Can a Dart enum have methods and fields?":
        "Yes, since Dart 2.17 enhanced enums can declare fields, constructors and methods; "
        "every value is a const instance, so the fields must be final.",
    "Why do I get 'RenderFlex overflowed by 42 pixels'?":
        "A Row/Column child wants more space than the parent gives. Wrap the child in Expanded or Flexible, "
        "or put the content in a scroll view; the yellow-black stripes are only shown in debug builds.",
    "How do I sign in with Google through Firebase Auth on both platforms?":
        "Use google_sign_in to get the id/access tokens, build a GoogleAuthProvider credential and call "
        "FirebaseAuth.instance.signInWithCredential. Android needs the SHA-1 in the Firebase console, iOS the reversed client id in Info.plist.",
    "How do I listen to Firestore changes in real time with a StreamBuilder?":
        "collection.snapshots() returns a Stream<QuerySnapshot>; hand it to a StreamBuilder and rebuild from snapshot.docs. "
        "Detach by disposing the widget — the listener is cancelled with the stream subscription.",
    "What is a MethodChannel and when do I need one?":
        "A named channel over which Dart sends a method name plus arguments to Kotlin/Swift and gets a result back. "
        "Use it when there is no plugin for the native API you need; keep the surface small and typed.",
    "Why does my channel call throw MissingPluginException?":
        "The native side never registered a handler for that channel name: a typo in the name, the plugin not registered "
        "in MainActivity/AppDelegate, or a hot restart after adding native code — a full rebuild fixes the last one.",
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

# Lecture text for FLT103: its topic plan is extracted from these headings (see qa/material.py)
MATERIAL_CODE = "FLT103"
DEMO_MATERIAL = """# Flutter 1 · Lecture 03 · State management

Today we look at how data flows through a Flutter app and when a package is worth it.

## setState and the widget lifecycle

A StatefulWidget owns a State object. Calling setState schedules a rebuild of this subtree only.
initState runs once, dispose runs when the element is removed; calling setState after dispose throws.
Keep setState for state that a single widget needs; lifting state up means moving it to the lowest
common ancestor.

## InheritedWidget, Provider and Riverpod

InheritedWidget propagates a value down the tree; descendants subscribe with
dependOnInheritedWidgetOfExactType. Provider wraps this: ChangeNotifier, ChangeNotifierProvider,
context.watch rebuilds the widget, context.read does not. Riverpod removes the BuildContext
dependency: providers are global, testable and can be overridden in tests. ValueNotifier is the
smallest ChangeNotifier; a StreamController is the reactive alternative.

## BLoC and app architecture

BLoC separates events from states with streams; good for large teams, more boilerplate.
Repositories talk to the network and the database, notifiers or blocs hold screen state,
widgets only render. Share state between tabs through a common ancestor, keep state when
navigating back by not disposing the notifier.
"""


def notes_for(title: str, topics: list[tuple[str, str]]) -> str:
    """Short lecture notes for a lecture without a real text: one section per topic (Markdown)."""
    lines = [f"# {title}", "", "Outline of the lecture — one section per topic of the plan.", ""]
    for topic_title, keywords in topics:
        words = [word.strip() for word in keywords.split(",") if word.strip()]
        lines += [
            f"## {topic_title}",
            "",
            f"Key terms: {', '.join(words)}.",
            f"We look at {topic_title.lower()} with live examples and the usual mistakes students make with it.",
            "",
        ]
    return "\n".join(lines)


MANUAL_TAG_SHARE = 0.25          # share of tagged questions whose tag counts as chosen by a person

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
    help = "Create 40 student accounts and 10 demo lectures with material, topics, 120+ tagged questions, answers, upvotes."

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

            # Topic plan: extracted from the real lecture text for one lecture, predefined for the
            # others (their material is a generated outline, one section per topic)
            if code == MATERIAL_CODE:
                LectureMaterial.objects.create(lecture=lecture, title="lecture-03-state-management.md",
                                               text=DEMO_MATERIAL, uploaded_by=lecturer)
                for order, section in enumerate(plan_from_text(DEMO_MATERIAL), start=1):
                    Topic.objects.create(lecture=lecture, title=section.title, keywords=", ".join(section.keywords),
                                         description=section.body, order=order)
            else:
                LectureMaterial.objects.create(lecture=lecture, title=f"{code.lower()}-notes.md",
                                               text=notes_for(title, DEMO_TOPICS[code]), uploaded_by=lecturer)
                for order, (topic_title, keywords) in enumerate(DEMO_TOPICS[code], start=1):
                    Topic.objects.create(lecture=lecture, title=topic_title, keywords=keywords, order=order)
            topics = list(lecture.topics.all())

            questions = []
            texts = DEMO_QUESTIONS[code]
            suggestions = tagging.suggest_topics(lecture, texts, topics)   # the real model tags the demo data
            for text, suggestion in zip(texts, suggestions):
                answered = (not is_open) and rng.random() < ANSWERED_SHARE
                if text in DEMO_ANSWERS:
                    answered = True  # a written answer implies the question is answered
                question = Question(lecture=lecture, text=text, author=rng.choice(students), is_answered=answered)
                if suggestion.tagged:
                    question.topic = suggestion.topic
                    if rng.random() < MANUAL_TAG_SHARE:
                        question.tag_source, question.tag_score = Question.TagSource.MANUAL, None
                    else:
                        question.tag_source, question.tag_score = Question.TagSource.AUTO, suggestion.score
                questions.append(question)
            Question.objects.bulk_create(questions)

            answers = [
                Answer(question=question, text=DEMO_ANSWERS[question.text], author=lecturer)
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
                for voter in rng.sample(students, votes):  # sample = unique user per question
                    upvotes.append(Upvote(question=question, user=voter))
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
                f"{questions_total} questions "
                f"({Question.objects.filter(lecture__code__in=codes, topic__isnull=False).count()} tagged), "
                f"{Answer.objects.filter(question__lecture__code__in=codes).count()} answers, "
                f"{LectureMaterial.objects.filter(lecture__code__in=codes).count()} materials, "
                f"{upvotes_total} upvotes from {STUDENTS} students."
            )
        )
