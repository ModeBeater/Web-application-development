import io
import json
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from . import tunnel
from .models import Lecture, Question, Upvote

DEMO_CODE = "KBTU26"  # created by the seed migration


class ApiTests(TestCase):
    """End-to-end tests of the JSON API against the real database engine."""

    def post_json(self, url, payload=None, **kwargs):
        return self.client.post(url, data=json.dumps(payload or {}), content_type="application/json", **kwargs)

    def test_health_reports_database_version(self):
        data = self.client.get(reverse("qa:health")).json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("PostgreSQL", data["database"])

    def test_seed_lecture_is_present(self):
        lecture = Lecture.objects.get(code=DEMO_CODE)
        self.assertEqual(lecture.questions.count(), 3)

    def test_create_lecture_returns_code_and_join_url(self):
        response = self.post_json(reverse("qa:api-lectures"), {"title": "  Lecture   one  "})
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["title"], "Lecture one")
        self.assertEqual(len(data["code"]), 6)
        self.assertTrue(data["join_url"].endswith(f"/l/{data['code']}/"))
        self.assertTrue(Lecture.objects.filter(code=data["code"]).exists())

    def test_create_lecture_requires_title(self):
        response = self.post_json(reverse("qa:api-lectures"), {"title": "   "})
        self.assertEqual(response.status_code, 400)
        self.assertIn("title", response.json()["error"])

    def test_list_lectures_counts_questions(self):
        data = self.client.get(reverse("qa:api-lectures")).json()
        demo = next(item for item in data["lectures"] if item["code"] == DEMO_CODE)
        self.assertEqual(demo["question_count"], 3)

    def test_ask_question_is_written_to_database(self):
        url = reverse("qa:api-lecture-questions", args=[DEMO_CODE.lower()])  # code is case-insensitive
        response = self.post_json(url, {"text": "Is EXPOSE enough to publish a port?", "author": "Yevgeniy"})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Question.objects.filter(text="Is EXPOSE enough to publish a port?").exists())
        self.assertIn("voter", response.cookies)
        self.assertEqual(response.json()["lecture_code"], DEMO_CODE)

    def test_ask_rejects_empty_and_too_long_text(self):
        url = reverse("qa:api-lecture-questions", args=[DEMO_CODE])
        self.assertEqual(self.post_json(url, {"text": ""}).status_code, 400)
        self.assertEqual(self.post_json(url, {"text": "x" * 501}).status_code, 400)
        self.assertEqual(self.client.post(url, data="not json", content_type="application/json").status_code, 400)

    def test_closed_lecture_rejects_questions(self):
        self.post_json(reverse("qa:api-toggle", args=[DEMO_CODE]))
        self.assertFalse(Lecture.objects.get(code=DEMO_CODE).is_open)
        response = self.post_json(reverse("qa:api-lecture-questions", args=[DEMO_CODE]), {"text": "Too late?"})
        self.assertEqual(response.status_code, 409)

    def test_upvote_toggles_and_reorders(self):
        lecture = Lecture.objects.get(code=DEMO_CODE)
        last = lecture.questions.order_by("created_at").last()  # has no votes yet
        url = reverse("qa:api-upvote", args=[last.id])

        first = self.post_json(url).json()
        self.assertEqual(first, {"id": last.id, "votes": 1, "voted": True})
        second = self.post_json(url).json()  # same cookie -> toggles off
        self.assertEqual(second, {"id": last.id, "votes": 0, "voted": False})

        # Three different voters push the question to the top of the list
        for voter in ("a", "b", "c"):
            self.post_json(url, {"voter": voter})
        self.assertEqual(Upvote.objects.filter(question=last).count(), 3)
        detail = self.client.get(reverse("qa:api-lecture", args=[DEMO_CODE])).json()
        self.assertEqual(detail["questions"][0]["id"], last.id)
        self.assertEqual(detail["questions"][0]["votes"], 3)

    def test_answered_questions_sink_to_the_bottom(self):
        lecture = Lecture.objects.get(code=DEMO_CODE)
        top = lecture.questions.order_by("created_at").first()  # 2 votes
        self.post_json(reverse("qa:api-answered", args=[top.id]))
        detail = self.client.get(reverse("qa:api-lecture", args=[DEMO_CODE])).json()
        self.assertEqual(detail["questions"][-1]["id"], top.id)
        self.assertTrue(detail["questions"][-1]["is_answered"])

    def test_unknown_lecture_is_404(self):
        response = self.client.get(reverse("qa:api-lecture", args=["NOPE42"]))
        self.assertEqual(response.status_code, 404)
        self.assertIn("NOPE42", response.json()["error"])  # JSON error, not an HTML page


class LectureCrudTests(TestCase):
    """Midterm: list / get by id / create / update / delete for the lecture resource."""

    def send(self, method, url, payload=None):
        return getattr(self.client, method)(url, data=json.dumps(payload or {}), content_type="application/json")

    def test_api_root_lists_resources_and_docs(self):
        data = self.client.get(reverse("qa:api-root")).json()
        self.assertEqual(data["version"], "1.0")
        self.assertTrue(data["docs"].endswith("/docs/"))
        self.assertTrue(data["resources"]["lectures"].endswith("/api/lectures/"))

    def test_get_by_numeric_id_and_by_code_are_the_same_lecture(self):
        lecture = Lecture.objects.get(code=DEMO_CODE)
        by_id = self.client.get(reverse("qa:api-lecture", args=[lecture.id])).json()
        by_code = self.client.get(reverse("qa:api-lecture", args=[DEMO_CODE.lower()])).json()
        self.assertEqual(by_id["id"], by_code["id"], lecture.id)
        self.assertEqual(by_id["question_count"], 3)
        self.assertEqual(len(by_id["questions"]), 3)
        self.assertEqual(self.client.get(reverse("qa:api-lecture", args=[999999])).status_code, 404)

    def test_list_supports_search_and_open_filter(self):
        self.send("post", reverse("qa:api-lectures"), {"title": "Closed one", "is_open": False})
        all_items = self.client.get(reverse("qa:api-lectures")).json()
        self.assertEqual(all_items["count"], 2)
        closed = self.client.get(reverse("qa:api-lectures"), {"is_open": "false"}).json()
        self.assertEqual([item["title"] for item in closed["lectures"]], ["Closed one"])
        found = self.client.get(reverse("qa:api-lectures"), {"q": "flutter"}).json()
        self.assertEqual(found["count"], 1)
        self.assertEqual(found["lectures"][0]["code"], DEMO_CODE)
        self.assertEqual(self.client.get(reverse("qa:api-lectures"), {"is_open": "maybe"}).status_code, 400)

    def test_put_replaces_and_patch_changes_only_given_fields(self):
        lecture = Lecture.objects.get(code=DEMO_CODE)
        url = reverse("qa:api-lecture", args=[lecture.id])

        response = self.send("put", url, {"title": "Renamed", "is_open": False})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Renamed")
        self.assertFalse(response.json()["is_open"])
        self.assertEqual(response.json()["code"], DEMO_CODE)  # the code never changes

        response = self.send("patch", url, {"is_open": True})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_open"])
        self.assertEqual(response.json()["title"], "Renamed")  # PATCH left the title alone

        self.assertEqual(self.send("put", url, {"is_open": True}).status_code, 400)  # PUT needs a title
        self.assertEqual(self.send("patch", url, {}).status_code, 400)  # PATCH needs at least one field
        self.assertEqual(self.send("patch", url, {"is_open": "yes"}).status_code, 400)  # must be boolean
        self.assertEqual(self.send("patch", url, {"title": "x" * 121}).status_code, 400)

        lecture.refresh_from_db()
        self.assertEqual((lecture.title, lecture.is_open), ("Renamed", True))

    def test_delete_removes_lecture_with_its_questions(self):
        lecture = Lecture.objects.get(code=DEMO_CODE)
        url = reverse("qa:api-lecture", args=[lecture.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertFalse(Lecture.objects.filter(pk=lecture.id).exists())
        self.assertEqual(Question.objects.count(), 0)  # cascade
        self.assertEqual(self.client.delete(url).status_code, 404)  # already gone

    def test_wrong_method_is_405(self):
        response = self.client.delete(reverse("qa:api-lectures"))
        self.assertEqual(response.status_code, 405)
        self.assertIn("GET", response["Allow"])


class QuestionCrudTests(TestCase):
    """Midterm: list / get by id / create / update / delete for the question resource."""

    def send(self, method, url, payload=None):
        return getattr(self.client, method)(url, data=json.dumps(payload or {}), content_type="application/json")

    def setUp(self):
        self.lecture = Lecture.objects.get(code=DEMO_CODE)
        self.question = self.lecture.questions.order_by("created_at").first()

    def test_list_all_questions_with_filters_and_pagination(self):
        other = Lecture.objects.create(title="Other")
        Question.objects.create(lecture=other, text="Other lecture question", is_answered=True)
        url = reverse("qa:api-questions")

        everything = self.client.get(url).json()
        self.assertEqual(everything["count"], 4)
        self.assertEqual(len(everything["questions"]), 4)
        self.assertIsNone(everything["limit"])

        page = self.client.get(url, {"limit": 2, "offset": 1}).json()
        self.assertEqual((page["count"], page["limit"], page["offset"], len(page["questions"])), (4, 2, 1, 2))

        by_lecture = self.client.get(url, {"lecture": self.lecture.id}).json()
        self.assertEqual(by_lecture["count"], 3)
        self.assertTrue(all(q["lecture_code"] == DEMO_CODE for q in by_lecture["questions"]))

        answered = self.client.get(url, {"answered": "true"}).json()
        self.assertEqual([q["text"] for q in answered["questions"]], ["Other lecture question"])

        self.assertEqual(self.client.get(url, {"q": "other"}).json()["count"], 1)
        self.assertEqual(self.client.get(url, {"limit": 0}).status_code, 400)
        self.assertEqual(self.client.get(url, {"limit": "ten"}).status_code, 400)
        self.assertEqual(self.client.get(url, {"lecture": "NOPE42"}).status_code, 404)

    def test_get_by_id_includes_votes(self):
        before = self.question.upvotes.count()  # the seed migration already gives it 2 votes
        Upvote.objects.create(question=self.question, voter_id="someone")
        data = self.client.get(reverse("qa:api-question", args=[self.question.id])).json()
        self.assertEqual(data["id"], self.question.id)
        self.assertEqual(data["lecture_id"], self.lecture.id)
        self.assertEqual(data["votes"], before + 1)
        self.assertEqual(self.client.get(reverse("qa:api-question", args=[999999])).status_code, 404)

    def test_list_questions_of_one_lecture(self):
        data = self.client.get(reverse("qa:api-lecture-questions", args=[self.lecture.id])).json()
        self.assertEqual(data["count"], 3)
        self.assertEqual(data["questions"][0]["votes"], 2)  # most upvoted first

    def test_put_and_patch_question(self):
        url = reverse("qa:api-question", args=[self.question.id])

        response = self.send("put", url, {"text": "Edited text", "author": "Editor", "is_answered": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "Edited text")
        self.assertEqual(response.json()["author"], "Editor")
        self.assertTrue(response.json()["is_answered"])

        response = self.send("put", url, {"text": "Only text"})  # PUT resets the optional fields
        self.assertEqual(response.json()["author"], "Anonymous")
        self.assertFalse(response.json()["is_answered"])

        response = self.send("patch", url, {"is_answered": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "Only text")
        self.assertTrue(response.json()["is_answered"])

        self.assertEqual(self.send("put", url, {"author": "no text"}).status_code, 400)
        self.assertEqual(self.send("patch", url, {}).status_code, 400)
        self.assertEqual(self.send("patch", url, {"text": "x" * 501}).status_code, 400)
        self.assertEqual(self.send("patch", reverse("qa:api-question", args=[999999]), {"text": "?"}).status_code, 404)

    def test_delete_question_and_its_upvotes(self):
        Upvote.objects.create(question=self.question, voter_id="someone")
        url = reverse("qa:api-question", args=[self.question.id])
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertFalse(Question.objects.filter(pk=self.question.id).exists())
        self.assertEqual(Upvote.objects.filter(question_id=self.question.id).count(), 0)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.assertEqual(self.lecture.questions.count(), 2)


class DocsTests(TestCase):
    def test_openapi_spec_is_served_and_covers_every_api_route(self):
        response = self.client.get(reverse("qa:openapi"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/yaml"))
        spec = response.content.decode()
        for route in (
            "/api/:", "/health/:", "/api/lectures/:", "/api/lectures/{key}/:", "/api/lectures/{key}/toggle/:",
            "/api/lectures/{key}/questions/:", "/api/questions/:", "/api/questions/{id}/:",
            "/api/questions/{id}/upvote/:", "/api/questions/{id}/answered/:",
        ):
            self.assertIn(route, spec)

    def test_docs_page_embeds_swagger_ui(self):
        response = self.client.get(reverse("qa:docs"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "swagger-ui-bundle.js")
        self.assertContains(response, '"/openapi.yaml"')


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
            data = self.client.get(reverse("qa:api-lecture", args=[DEMO_CODE])).json()
            screen = self.client.get(reverse("qa:screen", args=[DEMO_CODE]))
        self.assertEqual(data["join_url"], f"https://demo.trycloudflare.com/l/{DEMO_CODE}/")
        self.assertContains(screen, "via Cloudflare tunnel")

    def test_public_url_beats_tunnel(self):
        with self.settings(PUBLIC_URL="http://192.168.1.5:8000"), self.fake_metrics(b'{"hostname":"x.trycloudflare.com"}'):
            data = self.client.get(reverse("qa:api-lecture", args=[DEMO_CODE])).json()
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
        for name in ("qa:home",):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
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
                reverse("qa:api-lecture", args=[DEMO_CODE]),
                HTTP_HOST="demo.example.com",
                HTTP_X_FORWARDED_PROTO="https",
            )
        self.assertEqual(response.json()["join_url"], f"https://demo.example.com/l/{DEMO_CODE}/")
