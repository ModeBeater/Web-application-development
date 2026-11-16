import io
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from . import tunnel
from .models import Answer, Lecture, Question, Topic, Upvote

DEMO_CODE = "KBTU26"  # created by the seed migration


class LectureApiTests(APITestCase):
    """list / get by id / create / update / delete for the lecture resource (DRF)."""

    def test_api_root_links_everything(self):
        data = self.client.get(reverse("qa:api-root")).json()
        self.assertEqual(data["version"], "2.1")
        self.assertTrue(data["docs"].endswith("/docs/"))
        self.assertTrue(data["lectures"].endswith("/api/lectures/"))

    def test_health_reports_database_version(self):
        data = self.client.get(reverse("qa:health")).json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("PostgreSQL", data["database"])

    def test_list_is_paginated_and_counts_questions(self):
        data = self.client.get(reverse("qa:lecture-list")).json()
        self.assertEqual(set(data), {"count", "next", "previous", "results"})
        demo = next(item for item in data["results"] if item["code"] == DEMO_CODE)
        self.assertEqual(demo["question_count"], 3)

    def test_create_lecture_returns_201_with_code_and_join_url(self):
        response = self.client.post(reverse("qa:lecture-list"), {"title": "  Lecture   one  "}, format="json")
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["title"], "Lecture one")  # whitespace collapsed by validate_title
        self.assertEqual(len(data["code"]), 6)
        self.assertTrue(data["join_url"].endswith(f"/l/{data['code']}/"))
        self.assertEqual(data["question_count"], 0)
        self.assertTrue(Lecture.objects.filter(code=data["code"]).exists())

    def test_validation_errors_are_field_keyed(self):
        url = reverse("qa:lecture-list")
        self.assertEqual(self.client.post(url, {}, format="json").json(), {"title": ["This field is required."]})
        self.assertIn("title", self.client.post(url, {"title": "ab"}, format="json").json())
        self.assertIn("title", self.client.post(url, {"title": "x" * 121}, format="json").json())
        self.assertIn("is_open", self.client.post(url, {"title": "Fine", "is_open": "maybe"}, format="json").json())
        self.assertEqual(self.client.post(url, "not json", content_type="application/json").status_code, 400)

    def test_get_by_numeric_id_and_by_code_are_the_same_lecture(self):
        lecture = Lecture.objects.get(code=DEMO_CODE)
        by_id = self.client.get(reverse("qa:lecture-detail", args=[lecture.id])).json()
        by_code = self.client.get(reverse("qa:lecture-detail", args=[DEMO_CODE.lower()])).json()
        self.assertEqual(by_id["id"], by_code["id"], lecture.id)
        self.assertEqual(len(by_id["questions"]), 3)
        self.assertEqual(by_id["questions"][0]["votes"], 2)  # most upvoted first

    def test_unknown_lecture_is_json_404(self):
        response = self.client.get(reverse("qa:lecture-detail", args=["NOPE42"]))
        self.assertEqual(response.status_code, 404)
        self.assertIn("NOPE42", response.json()["detail"])
        self.assertEqual(self.client.get(reverse("qa:lecture-detail", args=[999999])).status_code, 404)

    def test_filters_search_and_ordering(self):
        self.client.post(reverse("qa:lecture-list"), {"title": "Closed one", "is_open": False}, format="json")
        url = reverse("qa:lecture-list")
        self.assertEqual(self.client.get(url).json()["count"], 2)
        closed = self.client.get(url, {"is_open": "false"}).json()
        self.assertEqual([item["title"] for item in closed["results"]], ["Closed one"])
        found = self.client.get(url, {"search": "flutter"}).json()
        self.assertEqual(found["count"], 1)
        self.assertEqual(found["results"][0]["code"], DEMO_CODE)
        by_title = self.client.get(url, {"ordering": "title"}).json()
        self.assertEqual([item["title"] for item in by_title["results"]], ["Closed one", "Flutter 1 · Lecture 00 · Course introduction"])

    def test_put_replaces_and_patch_changes_only_given_fields(self):
        lecture = Lecture.objects.get(code=DEMO_CODE)
        url = reverse("qa:lecture-detail", args=[lecture.id])

        response = self.client.put(url, {"title": "Renamed", "is_open": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json()["title"], response.json()["is_open"]), ("Renamed", False))
        self.assertEqual(response.json()["code"], DEMO_CODE)  # read-only, never changes

        response = self.client.patch(url, {"is_open": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json()["title"], response.json()["is_open"]), ("Renamed", True))

        self.assertEqual(self.client.put(url, {"is_open": True}, format="json").status_code, 400)  # PUT needs title
        self.assertEqual(self.client.patch(url, {"code": "HACKED"}, format="json").json()["code"], DEMO_CODE)

        lecture.refresh_from_db()
        self.assertEqual((lecture.title, lecture.is_open), ("Renamed", True))

    def test_delete_removes_lecture_with_its_questions(self):
        lecture = Lecture.objects.get(code=DEMO_CODE)
        url = reverse("qa:lecture-detail", args=[lecture.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertFalse(Lecture.objects.filter(pk=lecture.id).exists())
        self.assertEqual(Question.objects.count(), 0)  # cascade
        self.assertEqual(self.client.delete(url).status_code, 404)

    def test_wrong_method_is_405(self):
        response = self.client.delete(reverse("qa:lecture-list"))
        self.assertEqual(response.status_code, 405)
        self.assertIn("detail", response.json())

    def test_toggle_closes_and_rejects_questions(self):
        toggled = self.client.post(reverse("qa:lecture-toggle", args=[DEMO_CODE])).json()
        self.assertFalse(toggled["is_open"])
        response = self.client.post(reverse("qa:lecture-questions", args=[DEMO_CODE]), {"text": "Too late?"}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertIn("closed", response.json()["detail"])


class QuestionApiTests(APITestCase):
    """list / get by id / create / update / delete for the question resource (DRF)."""

    def setUp(self):
        self.lecture = Lecture.objects.get(code=DEMO_CODE)
        self.first = self.lecture.questions.order_by("created_at").first()  # 2 votes in the seed

    def test_ask_question_is_written_to_database(self):
        url = reverse("qa:lecture-questions", args=[DEMO_CODE.lower()])
        response = self.client.post(url, {"text": "Is EXPOSE enough to publish a port?", "author": "Yevgeniy"}, format="json")
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual((data["lecture_code"], data["author"], data["votes"]), (DEMO_CODE, "Yevgeniy", 0))
        self.assertNotIn("voter", data)  # write-only
        self.assertTrue(Question.objects.filter(text="Is EXPOSE enough to publish a port?").exists())
        self.assertIn("voter", response.cookies)

    def test_ask_rejects_empty_and_too_long_text(self):
        url = reverse("qa:lecture-questions", args=[DEMO_CODE])
        self.assertEqual(self.client.post(url, {"text": "   "}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {"text": "x" * 501}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {}, format="json").json(), {"text": ["This field is required."]})

    def test_list_questions_of_one_lecture_in_screen_order(self):
        data = self.client.get(reverse("qa:lecture-questions", args=[self.lecture.id])).json()
        self.assertEqual(data["count"], 3)
        self.assertEqual(data["results"][0]["id"], self.first.id)

    def test_list_all_questions_with_filters_search_ordering_pagination(self):
        other = Lecture.objects.create(title="Other")
        Question.objects.create(lecture=other, text="Other lecture question", is_answered=True)
        url = reverse("qa:question-list")

        everything = self.client.get(url).json()
        self.assertEqual((everything["count"], len(everything["results"])), (4, 4))
        self.assertIsNone(everything["next"])

        page = self.client.get(url, {"limit": 2, "offset": 1}).json()
        self.assertEqual((page["count"], len(page["results"])), (4, 2))
        self.assertIn("offset=3", page["next"])

        by_lecture = self.client.get(url, {"lecture": DEMO_CODE}).json()
        self.assertEqual(by_lecture["count"], 3)
        self.assertEqual(self.client.get(url, {"lecture": self.lecture.id}).json()["count"], 3)
        self.assertEqual(self.client.get(url, {"lecture": "NOPE42"}).status_code, 404)

        answered = self.client.get(url, {"is_answered": "true"}).json()
        self.assertEqual(
            [q["text"] for q in answered["results"]],
            ["Other lecture question", "Can I build iOS apps with Flutter on Windows?"],  # the latter has a seeded Answer
        )
        self.assertEqual(self.client.get(url, {"has_answer": "true"}).json()["count"], 1)
        self.assertEqual(self.client.get(url, {"has_answer": "false"}).json()["count"], 3)

        self.assertEqual(self.client.get(url, {"search": "other"}).json()["count"], 1)
        most_voted = self.client.get(url, {"ordering": "-votes"}).json()
        self.assertEqual(most_voted["results"][0]["id"], self.first.id)

        self.assertEqual(self.client.get(url, {"limit": 0}).json()["count"], 4)  # DRF ignores a bad limit

    def test_get_by_id_includes_votes_and_lecture(self):
        data = self.client.get(reverse("qa:question-detail", args=[self.first.id])).json()
        self.assertEqual((data["lecture_id"], data["votes"], data["voted"]), (self.lecture.id, 2, False))
        self.assertEqual(data["author"], "Aigerim")
        self.assertEqual(self.client.get(reverse("qa:question-detail", args=[999999])).status_code, 404)

    def test_put_and_patch_question(self):
        url = reverse("qa:question-detail", args=[self.first.id])
        response = self.client.put(url, {"text": "Edited text", "author": "Editor", "is_answered": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json()["text"], response.json()["author"], response.json()["is_answered"]), ("Edited text", "Editor", True))

        response = self.client.patch(url, {"author": ""}, format="json")
        self.assertEqual(response.json()["author"], "Anonymous")
        self.assertEqual(response.json()["text"], "Edited text")  # PATCH left the text alone

        self.assertEqual(self.client.put(url, {"author": "no text"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"text": "x" * 501}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"lecture_id": 999}, format="json").json()["lecture_id"], self.lecture.id)

    def test_delete_question_and_its_upvotes(self):
        url = reverse("qa:question-detail", args=[self.first.id])
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertFalse(Question.objects.filter(pk=self.first.id).exists())
        self.assertEqual(Upvote.objects.filter(question_id=self.first.id).count(), 0)
        self.assertEqual(self.client.delete(url).status_code, 404)

    def test_upvote_toggles_and_reorders(self):
        last = self.lecture.questions.order_by("created_at").last()  # no votes yet
        url = reverse("qa:question-upvote", args=[last.id])
        self.assertEqual(self.client.post(url).json(), {"id": last.id, "votes": 1, "voted": True})
        self.assertEqual(self.client.post(url).json(), {"id": last.id, "votes": 0, "voted": False})  # same cookie

        for voter in ("a", "b", "c"):
            self.client.post(url, {"voter": voter}, format="json")
        detail = self.client.get(reverse("qa:lecture-detail", args=[DEMO_CODE])).json()
        self.assertEqual((detail["questions"][0]["id"], detail["questions"][0]["votes"]), (last.id, 3))

    def test_answered_questions_sink_to_the_bottom(self):
        detail = self.client.get(reverse("qa:lecture-detail", args=[DEMO_CODE])).json()
        self.assertEqual(detail["questions"][0]["id"], self.first.id)  # most voted, not answered yet
        self.assertEqual(self.client.post(reverse("qa:question-answered", args=[self.first.id])).json(), {"id": self.first.id, "is_answered": True})
        detail = self.client.get(reverse("qa:lecture-detail", args=[DEMO_CODE])).json()
        flags = [q["is_answered"] for q in detail["questions"]]
        self.assertEqual(flags, sorted(flags))                       # open questions first, answered ones last
        self.assertEqual(detail["questions"][-2]["id"], self.first.id)  # among the answered: more votes first


class TopicApiTests(APITestCase):
    """Topics: one lecture -> many topics (FK CASCADE); a question may be tagged with a topic of its lecture."""

    def setUp(self):
        self.lecture = Lecture.objects.get(code=DEMO_CODE)
        self.topic = self.lecture.topics.first()           # "Dart language" from the seed migration
        self.other = Lecture.objects.create(title="Another lecture")
        self.other_topic = Topic.objects.create(lecture=self.other, title="Foreign topic")

    def test_lecture_lists_its_topics_with_question_counts(self):
        data = self.client.get(reverse("qa:lecture-topics", args=[DEMO_CODE])).json()
        self.assertEqual(data["count"], 3)
        self.assertEqual([t["title"] for t in data["results"]], ["Dart language", "Tooling and setup", "Platforms"])
        self.assertEqual(data["results"][0]["question_count"], 1)
        detail = self.client.get(reverse("qa:lecture-detail", args=[DEMO_CODE])).json()
        self.assertEqual(detail["topic_count"], 3)
        self.assertEqual(len(detail["topics"]), 3)

    def test_create_topic_inside_lecture_validates_and_normalizes(self):
        url = reverse("qa:lecture-topics", args=[DEMO_CODE])
        response = self.client.post(url, {"title": "  Hot   reload ", "keywords": "Hot Reload, restart , "}, format="json")
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual((data["title"], data["keywords"], data["lecture_code"]), ("Hot reload", "hot reload, restart", DEMO_CODE))
        self.assertEqual(Topic.objects.get(pk=data["id"]).lecture_id, self.lecture.id)
        # same title again -> field error, not a 500 from the unique constraint
        self.assertEqual(self.client.post(url, {"title": "hot reload"}, format="json").status_code, 400)
        self.assertIn("title", self.client.post(url, {"title": "ab"}, format="json").json())
        self.assertEqual(self.client.post(reverse("qa:lecture-topics", args=["NOPE42"]), {"title": "x"}, format="json").status_code, 404)

    def test_topic_crud_and_filters(self):
        url = reverse("qa:topic-detail", args=[self.topic.id])
        self.assertEqual(self.client.get(url).json()["title"], "Dart language")
        self.assertEqual(self.client.patch(url, {"keywords": "dart, null-safety"}, format="json").json()["keywords"], "dart, null-safety")
        self.assertEqual(self.client.put(url, {"title": "Dart", "order": 5}, format="json").json()["order"], 5)
        self.assertEqual(self.client.get(reverse("qa:topic-list"), {"lecture": DEMO_CODE.lower()}).json()["count"], 3)
        self.assertEqual(self.client.get(reverse("qa:topic-list"), {"lecture": "NOPE42"}).status_code, 404)
        self.assertEqual(self.client.get(reverse("qa:topic-detail", args=[9999])).status_code, 404)
        self.assertEqual(self.client.post(reverse("qa:topic-list"), {"title": "x"}, format="json").status_code, 405)

    def test_topic_questions_endpoint_and_question_filter(self):
        data = self.client.get(reverse("qa:topic-questions", args=[self.topic.id])).json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["topic_title"], "Dart language")
        filtered = self.client.get(reverse("qa:question-list"), {"topic": self.topic.id}).json()
        self.assertEqual(filtered["count"], 1)
        self.assertEqual(self.client.get(reverse("qa:question-list"), {"topic": "abc"}).status_code, 400)

    def test_question_can_only_be_tagged_with_a_topic_of_its_lecture(self):
        url = reverse("qa:lecture-questions", args=[DEMO_CODE])
        bad = self.client.post(url, {"text": "Wrong topic?", "topic_id": self.other_topic.id}, format="json")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json(), {"topic_id": ["This topic belongs to another lecture."]})
        self.assertEqual(self.client.post(url, {"text": "Missing topic?", "topic_id": 9999}, format="json").status_code, 400)

        good = self.client.post(url, {"text": "Is Dart similar to Kotlin?", "topic_id": self.topic.id}, format="json")
        self.assertEqual(good.status_code, 201)
        self.assertEqual((good.json()["topic_id"], good.json()["topic_title"]), (self.topic.id, "Dart language"))
        # re-tag, un-tag, and a foreign topic on PATCH
        detail = reverse("qa:question-detail", args=[good.json()["id"]])
        self.assertEqual(self.client.patch(detail, {"topic_id": None}, format="json").json()["topic_title"], None)
        self.assertEqual(self.client.patch(detail, {"topic_id": self.other_topic.id}, format="json").status_code, 400)

    def test_deleting_topic_keeps_questions_and_deleting_lecture_cascades(self):
        question = self.topic.questions.first()
        self.assertEqual(self.client.delete(reverse("qa:topic-detail", args=[self.topic.id])).status_code, 204)
        question.refresh_from_db()
        self.assertIsNone(question.topic_id)                       # SET_NULL: the question survives
        self.assertTrue(Question.objects.filter(pk=question.pk).exists())

        Topic.objects.create(lecture=self.other, title="Second")
        self.assertEqual(self.other.topics.count(), 2)
        self.client.delete(reverse("qa:lecture-detail", args=[self.other.id]))
        self.assertEqual(Topic.objects.filter(lecture_id=self.other.id).count(), 0)   # CASCADE


class AnswerApiTests(APITestCase):
    """Answer: one question -> one written answer (OneToOneField CASCADE)."""

    def setUp(self):
        self.lecture = Lecture.objects.get(code=DEMO_CODE)
        self.answered = Question.objects.get(lecture=self.lecture, answer__isnull=False)   # from the seed migration
        self.open = Question.objects.filter(lecture=self.lecture, answer__isnull=True).first()

    def test_seeded_answer_is_embedded_in_the_question(self):
        data = self.client.get(reverse("qa:question-detail", args=[self.answered.id])).json()
        self.assertTrue(data["is_answered"])
        self.assertIn("Xcode", data["answer"]["text"])
        self.assertEqual(data["answer"]["question_id"], self.answered.id)
        open_data = self.client.get(reverse("qa:question-detail", args=[self.open.id])).json()
        self.assertIsNone(open_data["answer"])

    def test_put_creates_then_replaces_the_answer_and_marks_answered(self):
        url = reverse("qa:question-answer", args=[self.open.id])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.put(url, {"text": "   "}, format="json").status_code, 400)

        created = self.client.put(url, {"text": "Yes - the basics are enough.", "author": "Lecturer"}, format="json")
        self.assertEqual(created.status_code, 201)
        self.open.refresh_from_db()
        self.assertTrue(self.open.is_answered)
        self.assertEqual(Answer.objects.filter(question=self.open).count(), 1)

        replaced = self.client.put(url, {"text": "Updated answer"}, format="json")
        self.assertEqual(replaced.status_code, 200)
        self.assertEqual(replaced.json()["id"], created.json()["id"])          # still one row (one-to-one)
        self.assertEqual(self.client.get(url).json()["text"], "Updated answer")
        self.assertEqual(self.client.get(reverse("qa:question-list"), {"lecture": DEMO_CODE, "has_answer": "true"}).json()["count"], 2)

    def test_delete_answer_reopens_question_and_404_without_answer(self):
        url = reverse("qa:question-answer", args=[self.answered.id])
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.answered.refresh_from_db()
        self.assertFalse(self.answered.is_answered)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.assertEqual(self.client.get(reverse("qa:question-answer", args=[9999])).status_code, 404)

    def test_deleting_question_cascades_to_its_answer(self):
        answer_id = self.answered.answer.id
        self.assertEqual(self.client.delete(reverse("qa:question-detail", args=[self.answered.id])).status_code, 204)
        self.assertFalse(Answer.objects.filter(pk=answer_id).exists())


class DocsTests(APITestCase):
    def test_schema_is_generated_and_covers_every_route(self):
        response = self.client.get(reverse("qa:schema"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"].split(";")[0], "application/vnd.oai.openapi")  # YAML by default
        spec = response.content.decode()
        for route in (
            "/api/:", "/health/:", "/api/lectures/:", "/api/lectures/{key}/:", "/api/lectures/{key}/toggle/:",
            "/api/lectures/{key}/questions/:", "/api/questions/:", "/api/questions/{id}/:",
            "/api/questions/{id}/upvote/:", "/api/questions/{id}/answered/:", "/api/questions/{id}/answer/:",
            "/api/lectures/{key}/topics/:", "/api/topics/:", "/api/topics/{id}/:", "/api/topics/{id}/questions/:",
        ):
            self.assertIn(route, spec)
        self.assertEqual(self.client.get(reverse("qa:schema"), {"format": "json"})["Content-Type"].split(";")[0], "application/vnd.oai.openapi+json")

    def test_docs_page_embeds_swagger_ui(self):
        response = self.client.get(reverse("qa:docs"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "swagger-ui")

    def test_browsable_api_renders_in_a_browser(self):
        response = self.client.get(reverse("qa:lecture-list"), HTTP_ACCEPT="text/html")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lecture List")


class WaitForDbTests(TestCase):
    def test_reports_database_is_up(self):
        out = StringIO()
        call_command("wait_for_db", attempts=1, stdout=out)
        self.assertIn("Database is up.", out.getvalue())


class SeedDemoTests(TestCase):
    def test_seed_creates_100_plus_questions_and_is_idempotent(self):
        out = StringIO()
        call_command("seed_demo", stdout=out)
        self.assertIn("Seeded 8 lectures", out.getvalue())
        self.assertEqual(Lecture.objects.filter(code__startswith="FLT").count(), 8)
        self.assertGreaterEqual(Question.objects.count(), 100)
        self.assertGreater(Upvote.objects.count(), 100)
        self.assertEqual(Topic.objects.filter(lecture__code__startswith="FLT").count(), 24)
        self.assertEqual(Answer.objects.filter(question__lecture__code__startswith="FLT").count(), 8)
        self.assertGreater(Question.objects.filter(topic__isnull=False).count(), 90)
        self.assertTrue(all(q.is_answered for q in Question.objects.filter(answer__isnull=False)))
        self.assertTrue(Question.objects.filter(is_answered=True).exists())

        questions_before = Question.objects.count()
        call_command("seed_demo", stdout=StringIO())      # second run: no duplicates
        self.assertEqual(Question.objects.count(), questions_before)
        call_command("seed_demo", clear=True, stdout=StringIO())  # regenerate: same totals
        self.assertEqual(Question.objects.count(), questions_before)

    def test_seeded_timestamps_are_in_the_past(self):
        call_command("seed_demo", stdout=StringIO())
        from django.utils import timezone

        self.assertFalse(Question.objects.filter(created_at__gt=timezone.now()).exists())

    def test_home_page_shows_totals(self):
        call_command("seed_demo", stdout=StringIO())
        response = self.client.get(reverse("qa:home"))
        self.assertContains(response, f"<strong>{Question.objects.count()}</strong> questions")


class TunnelDiscoveryTests(TestCase):
    """The QR code follows the optional cloudflared tunnel without any manual configuration."""

    def setUp(self):
        tunnel.forget_cached_tunnel_url()

    def tearDown(self):
        tunnel.forget_cached_tunnel_url()

    @staticmethod
    def fake_metrics(payload: bytes):
        """Pretend cloudflared answered GET /quicktunnel with this body (BytesIO works as a context manager)."""
        return mock.patch("qa.tunnel.urllib.request.urlopen", return_value=io.BytesIO(payload))

    def test_join_url_uses_running_tunnel(self):
        with self.settings(PUBLIC_URL=""), self.fake_metrics(b'{"hostname":"demo.trycloudflare.com"}'):
            data = self.client.get(reverse("qa:lecture-detail", args=[DEMO_CODE])).json()
            screen = self.client.get(reverse("qa:screen", args=[DEMO_CODE]))
        self.assertEqual(data["join_url"], f"https://demo.trycloudflare.com/l/{DEMO_CODE}/")
        self.assertContains(screen, "via Cloudflare tunnel")

    def test_public_url_beats_tunnel(self):
        with self.settings(PUBLIC_URL="http://192.168.1.5:8000"), self.fake_metrics(b'{"hostname":"x.trycloudflare.com"}'):
            data = self.client.get(reverse("qa:lecture-detail", args=[DEMO_CODE])).json()
        self.assertTrue(data["join_url"].startswith("http://192.168.1.5:8000/"))

    def test_lookup_is_cached(self):
        with self.fake_metrics(b'{"hostname":"demo.trycloudflare.com"}') as urlopen:
            for _ in range(5):
                tunnel.tunnel_public_url()
        self.assertEqual(urlopen.call_count, 1)

    def test_no_tunnel_falls_back_to_request_and_warns_on_localhost(self):
        with self.settings(PUBLIC_URL=""), mock.patch("qa.tunnel.urllib.request.urlopen", side_effect=OSError("no tunnel")):
            screen = self.client.get(reverse("qa:screen", args=[DEMO_CODE]), HTTP_HOST="localhost:8000")
        self.assertContains(screen, f"http://localhost:8000/l/{DEMO_CODE}/")
        self.assertContains(screen, "works only on this computer")


class PageTests(TestCase):
    def test_pages_render(self):
        self.assertEqual(self.client.get(reverse("qa:home")).status_code, 200)
        for name in ("qa:lecture", "qa:screen"):
            self.assertEqual(self.client.get(reverse(name, args=[DEMO_CODE])).status_code, 200)

    def test_screen_contains_qr_with_public_url(self):
        with self.settings(PUBLIC_URL="http://192.168.1.5:8000"):
            response = self.client.get(reverse("qa:screen", args=[DEMO_CODE]))
        self.assertContains(response, "<svg")
        self.assertContains(response, "viewBox=")  # scalable: a fixed-size SVG gets clipped by the panel
        self.assertContains(response, f"http://192.168.1.5:8000/l/{DEMO_CODE}/")

    def test_join_url_follows_the_request_host_and_forwarded_https(self):
        """Without PUBLIC_URL and tunnel the QR uses the request host; behind a proxy that is https."""
        tunnel.forget_cached_tunnel_url()
        with self.settings(PUBLIC_URL="", TUNNEL_METRICS_URL="", ALLOWED_HOSTS=["demo.example.com"]):
            response = self.client.get(
                reverse("qa:lecture-detail", args=[DEMO_CODE]),
                HTTP_HOST="demo.example.com",
                HTTP_X_FORWARDED_PROTO="https",
            )
        self.assertEqual(response.json()["join_url"], f"https://demo.example.com/l/{DEMO_CODE}/")
