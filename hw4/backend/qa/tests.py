import io
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from . import tunnel
from .models import Lecture, Question, Upvote

User = get_user_model()
DEMO_CODE = "KBTU26"  # created by the seed migration together with the demo accounts
PASSWORD = "Demo12345!"  # DEMO_PASSWORD default


class AuthenticatedMixin:
    """Demo accounts from the seed migration, handy in every test class."""

    def setUp(self):
        self.admin = User.objects.get(username="admin")
        self.lecturer = User.objects.get(username="lecturer")
        self.student = User.objects.get(username="student")
        self.lecture = Lecture.objects.get(code=DEMO_CODE)

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def anonymous(self):
        return APIClient()  # a fresh client without credentials


# ---------------------------------------------------------------------------
# Authentication: register / login / refresh / logout / profile
# ---------------------------------------------------------------------------


class AuthFlowTests(APITestCase):
    def login(self, username="student", password=PASSWORD):
        return self.client.post(reverse("accounts:login"), {"username": username, "password": password}, format="json")

    def test_register_creates_user_and_signs_in(self):
        response = self.client.post(
            reverse("accounts:register"),
            {"username": "newbie", "password": "Str0ng-pass-42", "first_name": "New", "role": "lecturer", "email": "n@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(set(data), {"access", "refresh", "user"})
        self.assertEqual((data["user"]["username"], data["user"]["role"], data["user"]["display_name"]), ("newbie", "lecturer", "New"))
        user = User.objects.get(username="newbie")
        self.assertTrue(user.check_password("Str0ng-pass-42"))  # hashed, not stored in clear
        self.assertNotIn("password", data["user"])

    def test_register_validates_input(self):
        url = reverse("accounts:register")
        self.assertIn("password", self.client.post(url, {"username": "weak", "password": "12345678"}, format="json").json())
        self.assertIn("username", self.client.post(url, {"username": "student", "password": "Str0ng-pass-42"}, format="json").json())  # taken
        self.assertIn("role", self.client.post(url, {"username": "sneaky", "password": "Str0ng-pass-42", "role": "admin"}, format="json").json())
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 400)

    def test_login_returns_tokens_with_role_claim_and_user(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["user"]["username"], "student")
        self.assertEqual(data["user"]["role"], "student")
        from rest_framework_simplejwt.tokens import AccessToken

        claims = AccessToken(data["access"])
        self.assertEqual((claims["role"], claims["username"]), ("student", "student"))
        self.assertEqual(self.login(password="wrong").status_code, 401)

    def test_bearer_token_authenticates_requests(self):
        access = self.login().json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        me = self.client.get(reverse("accounts:me"))
        self.assertEqual((me.status_code, me.json()["username"]), (200, "student"))
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not-a-token")
        self.assertEqual(self.client.get(reverse("accounts:me")).status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.get(reverse("accounts:me")).status_code, 401)

    def test_refresh_rotates_and_blacklists_the_old_token(self):
        refresh = self.login().json()["refresh"]
        rotated = self.client.post(reverse("accounts:refresh"), {"refresh": refresh}, format="json")
        self.assertEqual(rotated.status_code, 200)
        self.assertEqual(set(rotated.json()), {"access", "refresh"})
        self.assertNotEqual(rotated.json()["refresh"], refresh)
        reused = self.client.post(reverse("accounts:refresh"), {"refresh": refresh}, format="json")
        self.assertEqual(reused.status_code, 401)
        self.assertEqual(reused.json()["code"], "token_not_valid")

    def test_logout_revokes_refresh_token(self):
        tokens = self.login().json()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        response = self.client.post(reverse("accounts:logout"), {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(response.status_code, 205)
        self.assertEqual(self.client.post(reverse("accounts:refresh"), {"refresh": tokens["refresh"]}, format="json").status_code, 401)
        self.assertEqual(self.client.post(reverse("accounts:logout"), {"refresh": "garbage"}, format="json").status_code, 400)

    def test_profile_read_edit_and_password_change(self):
        access = self.login().json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        me = self.client.get(reverse("accounts:me")).json()
        self.assertEqual(me["stats"]["questions"], 1)  # from the seed migration
        edited = self.client.patch(reverse("accounts:me"), {"first_name": "Yevgeniy", "role": "admin"}, format="json").json()
        self.assertEqual((edited["first_name"], edited["role"]), ("Yevgeniy", "student"))  # role is read-only here

        wrong = self.client.post(reverse("accounts:password"), {"current_password": "nope", "new_password": "Another-pass-9"}, format="json")
        self.assertEqual(wrong.status_code, 400)
        ok = self.client.post(reverse("accounts:password"), {"current_password": PASSWORD, "new_password": "Another-pass-9"}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.login(password="Another-pass-9").status_code, 200)


# ---------------------------------------------------------------------------
# Roles and permissions
# ---------------------------------------------------------------------------


class PermissionTests(AuthenticatedMixin, APITestCase):
    def test_reading_is_public(self):
        client = self.anonymous()
        self.assertEqual(client.get(reverse("qa:lecture-list")).status_code, 200)
        self.assertEqual(client.get(reverse("qa:lecture-detail", args=[DEMO_CODE])).status_code, 200)
        self.assertEqual(client.get(reverse("qa:question-list")).status_code, 200)
        self.assertEqual(client.get(reverse("qa:stats")).status_code, 200)

    def test_writing_needs_a_token(self):
        client = self.anonymous()
        self.assertEqual(client.post(reverse("qa:lecture-list"), {"title": "Anon"}, format="json").status_code, 401)
        self.assertEqual(client.post(reverse("qa:lecture-questions", args=[DEMO_CODE]), {"text": "Anon?"}, format="json").status_code, 401)
        self.assertEqual(client.post(reverse("qa:question-upvote", args=[1])).status_code, 401)
        self.assertEqual(client.get(reverse("accounts:me")).status_code, 401)

    def test_only_lecturers_create_lectures_and_become_owners(self):
        self.assertEqual(self.as_(self.student).post(reverse("qa:lecture-list"), {"title": "Mine"}, format="json").status_code, 403)
        response = self.as_(self.lecturer).post(reverse("qa:lecture-list"), {"title": "Mine"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["owner"]["username"], "lecturer")
        self.assertTrue(response.json()["can_manage"])
        self.assertEqual(self.as_(self.admin).post(reverse("qa:lecture-list"), {"title": "Admin's"}, format="json").status_code, 201)

    def test_only_owner_or_admin_manage_a_lecture(self):
        other = User.objects.create_user("other_lecturer", password=PASSWORD, role="lecturer")
        url = reverse("qa:lecture-detail", args=[self.lecture.id])
        for user in (self.student, other):
            self.assertEqual(self.as_(user).patch(url, {"title": "Hijacked"}, format="json").status_code, 403)
            self.assertEqual(self.as_(user).post(reverse("qa:lecture-toggle", args=[DEMO_CODE])).status_code, 403)
            self.assertEqual(self.as_(user).delete(url).status_code, 403)
        self.assertEqual(self.as_(self.lecturer).patch(url, {"title": "Renamed by owner"}, format="json").status_code, 200)
        self.assertEqual(self.as_(self.admin).patch(url, {"title": "Renamed by admin"}, format="json").status_code, 200)
        self.assertFalse(self.as_(self.student).get(url).json()["can_manage"])
        self.assertTrue(self.as_(self.lecturer).get(url).json()["can_manage"])
        self.assertEqual(self.as_(self.admin).delete(url).status_code, 204)

    def test_any_user_asks_and_upvotes_and_becomes_author(self):
        response = self.as_(self.student).post(reverse("qa:lecture-questions", args=[DEMO_CODE]), {"text": "May I?"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["author"]["username"], "student")
        self.assertTrue(response.json()["can_edit"])
        self.assertFalse(response.json()["can_answer"])
        qid = response.json()["id"]
        self.assertEqual(self.as_(self.lecturer).post(reverse("qa:question-upvote", args=[qid])).json()["votes"], 1)
        self.assertEqual(self.as_(self.lecturer).post(reverse("qa:question-upvote", args=[qid])).json()["votes"], 0)  # toggle
        self.assertEqual(Question.objects.get(pk=qid).author, self.student)

    def test_question_edit_delete_rules(self):
        aigerim = User.objects.get(username="aigerim")
        question = self.lecture.questions.get(author=aigerim)
        url = reverse("qa:question-detail", args=[question.id])
        self.assertEqual(self.as_(self.student).patch(url, {"text": "Not mine"}, format="json").status_code, 403)
        self.assertEqual(self.as_(self.student).delete(url).status_code, 403)
        self.assertEqual(self.as_(aigerim).patch(url, {"text": "Mine, edited"}, format="json").status_code, 200)
        self.assertEqual(self.as_(self.lecturer).patch(url, {"text": "Owner edits"}, format="json").status_code, 200)
        self.assertIn("is_answered", self.as_(aigerim).patch(url, {"is_answered": True}, format="json").json())  # 400
        self.assertEqual(self.as_(self.lecturer).patch(url, {"is_answered": True}, format="json").status_code, 200)
        self.assertEqual(self.as_(self.admin).delete(url).status_code, 204)

    def test_only_lecture_owner_marks_answered(self):
        question = self.lecture.questions.first()
        url = reverse("qa:question-answered", args=[question.id])
        self.assertEqual(self.as_(self.student).post(url).status_code, 403)
        self.assertEqual(self.as_(self.lecturer).post(url).json()["is_answered"], True)
        self.assertEqual(self.as_(self.admin).post(url).json()["is_answered"], False)

    def test_user_management_is_admin_only(self):
        url = reverse("accounts:user-list")
        self.assertEqual(self.anonymous().get(url).status_code, 401)
        self.assertEqual(self.as_(self.student).get(url).status_code, 403)
        self.assertEqual(self.as_(self.lecturer).get(url).status_code, 403)
        listing = self.as_(self.admin).get(url, {"role": "student", "search": "aig"}).json()
        self.assertEqual([u["username"] for u in listing["results"]], ["aigerim"])

        detail = reverse("accounts:user-detail", args=[self.student.id])
        promoted = self.as_(self.admin).patch(detail, {"role": "lecturer", "is_active": False}, format="json").json()
        self.assertEqual((promoted["role"], promoted["is_active"]), ("lecturer", False))
        self.assertEqual(self.client.post(reverse("accounts:login"), {"username": "student", "password": PASSWORD}, format="json").status_code, 401)  # inactive

        me = reverse("accounts:user-detail", args=[self.admin.id])
        self.assertEqual(self.as_(self.admin).patch(me, {"role": "student"}, format="json").status_code, 400)
        self.assertEqual(self.as_(self.admin).delete(me).status_code, 400)
        self.assertEqual(self.as_(self.admin).delete(detail).status_code, 204)
        self.assertFalse(User.objects.filter(username="student").exists())


# ---------------------------------------------------------------------------
# CRUD, filters, pagination (as in HW3, now with ownership)
# ---------------------------------------------------------------------------


class LectureApiTests(AuthenticatedMixin, APITestCase):
    def test_api_root_links_everything(self):
        data = self.client.get(reverse("qa:api-root")).json()
        self.assertEqual(data["version"], "3.0")
        self.assertTrue(data["auth"]["login"].endswith("/api/auth/login/"))
        self.assertTrue(data["users"].endswith("/api/users/"))

    def test_health_reports_database_version(self):
        data = self.client.get(reverse("qa:health")).json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("PostgreSQL", data["database"])

    def test_list_is_paginated_with_owner_and_counts(self):
        data = self.client.get(reverse("qa:lecture-list")).json()
        self.assertEqual(set(data), {"count", "next", "previous", "results"})
        demo = next(item for item in data["results"] if item["code"] == DEMO_CODE)
        self.assertEqual((demo["question_count"], demo["owner"]["username"]), (3, "lecturer"))

    def test_create_validates_and_returns_201(self):
        client = self.as_(self.lecturer)
        response = client.post(reverse("qa:lecture-list"), {"title": "  Lecture   one  "}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["title"], "Lecture one")
        self.assertEqual(len(response.json()["code"]), 6)
        self.assertEqual(client.post(reverse("qa:lecture-list"), {"title": "ab"}, format="json").json(), {"title": ["Title must be at least 3 characters."]})
        self.assertIn("is_open", client.post(reverse("qa:lecture-list"), {"title": "Fine", "is_open": "maybe"}, format="json").json())

    def test_get_by_numeric_id_and_by_code_are_the_same_lecture(self):
        by_id = self.client.get(reverse("qa:lecture-detail", args=[self.lecture.id])).json()
        by_code = self.client.get(reverse("qa:lecture-detail", args=[DEMO_CODE.lower()])).json()
        self.assertEqual(by_id["id"], by_code["id"], self.lecture.id)
        self.assertEqual(len(by_id["questions"]), 3)
        self.assertEqual(by_id["questions"][0]["votes"], 2)  # most upvoted first
        self.assertEqual(by_id["questions"][0]["author"]["display_name"], "Aigerim S.")
        response = self.client.get(reverse("qa:lecture-detail", args=["NOPE42"]))
        self.assertEqual((response.status_code, "NOPE42" in response.json()["detail"]), (404, True))

    def test_filters_search_ordering_and_mine(self):
        self.as_(self.admin).post(reverse("qa:lecture-list"), {"title": "Closed one", "is_open": False}, format="json")
        url = reverse("qa:lecture-list")
        self.assertEqual(self.anonymous().get(url).json()["count"], 2)
        self.assertEqual([l["title"] for l in self.client.get(url, {"is_open": "false"}).json()["results"]], ["Closed one"])
        self.assertEqual(self.client.get(url, {"search": "flutter"}).json()["results"][0]["code"], DEMO_CODE)
        self.assertEqual(self.client.get(url, {"search": "tashimov"}).json()["count"], 1)  # owner name
        self.assertEqual(self.anonymous().get(url, {"owner": "me"}).status_code, 401)
        self.assertEqual([l["code"] for l in self.as_(self.lecturer).get(url, {"owner": "me"}).json()["results"]], [DEMO_CODE])
        self.assertEqual(self.as_(self.admin).get(url, {"owner": "me"}).json()["count"], 1)

    def test_put_patch_delete_by_owner(self):
        client = self.as_(self.lecturer)
        url = reverse("qa:lecture-detail", args=[self.lecture.id])
        self.assertEqual(client.put(url, {"title": "Renamed", "is_open": False}, format="json").json()["is_open"], False)
        self.assertEqual(client.patch(url, {"is_open": True}, format="json").json()["title"], "Renamed")
        self.assertEqual(client.patch(url, {"code": "HACKED"}, format="json").json()["code"], DEMO_CODE)
        self.assertEqual(client.put(url, {"is_open": True}, format="json").status_code, 400)
        self.assertEqual(client.delete(url).status_code, 204)
        self.assertEqual(Question.objects.count(), 0)  # cascade
        self.assertEqual(client.delete(url).status_code, 404)

    def test_toggle_closes_and_rejects_questions(self):
        self.assertFalse(self.as_(self.lecturer).post(reverse("qa:lecture-toggle", args=[DEMO_CODE])).json()["is_open"])
        response = self.as_(self.student).post(reverse("qa:lecture-questions", args=[DEMO_CODE]), {"text": "Too late?"}, format="json")
        self.assertEqual((response.status_code, "closed" in response.json()["detail"]), (409, True))


class QuestionApiTests(AuthenticatedMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.first = self.lecture.questions.order_by("created_at").first()  # 2 votes in the seed

    def test_ask_validates_text(self):
        url = reverse("qa:lecture-questions", args=[DEMO_CODE])
        client = self.as_(self.student)
        self.assertEqual(client.post(url, {"text": "   "}, format="json").status_code, 400)
        self.assertEqual(client.post(url, {"text": "x" * 501}, format="json").status_code, 400)
        self.assertEqual(client.post(url, {}, format="json").json(), {"text": ["This field is required."]})

    def test_list_questions_of_one_lecture_in_screen_order(self):
        data = self.client.get(reverse("qa:lecture-questions", args=[self.lecture.id])).json()
        self.assertEqual((data["count"], data["results"][0]["id"]), (3, self.first.id))

    def test_list_all_with_filters_search_ordering_pagination(self):
        other = Lecture.objects.create(title="Other", owner=self.lecturer)
        Question.objects.create(lecture=other, text="Other lecture question", is_answered=True, author=self.student)
        url = reverse("qa:question-list")

        everything = self.client.get(url).json()
        self.assertEqual((everything["count"], len(everything["results"]), everything["next"]), (4, 4, None))
        page = self.client.get(url, {"limit": 2, "offset": 1}).json()
        self.assertEqual((page["count"], len(page["results"])), (4, 2))
        self.assertIn("offset=3", page["next"])
        self.assertEqual(self.client.get(url, {"lecture": DEMO_CODE}).json()["count"], 3)
        self.assertEqual(self.client.get(url, {"lecture": "NOPE42"}).status_code, 404)
        self.assertEqual([q["text"] for q in self.client.get(url, {"is_answered": "true"}).json()["results"]], ["Other lecture question"])
        self.assertEqual(self.client.get(url, {"search": "aigerim"}).json()["count"], 1)  # author name
        self.assertEqual(self.client.get(url, {"ordering": "-votes"}).json()["results"][0]["id"], self.first.id)
        self.assertEqual(self.as_(self.student).get(url, {"author": "me"}).json()["count"], 2)

    def test_voted_flag_follows_the_caller(self):
        url = reverse("qa:question-detail", args=[self.first.id])
        self.assertFalse(self.anonymous().get(url).json()["voted"])
        self.assertTrue(self.as_(User.objects.get(username="daniyar")).get(url).json()["voted"])
        self.assertFalse(self.as_(self.lecturer).get(url).json()["voted"])

    def test_answered_questions_sink_to_the_bottom(self):
        self.as_(self.lecturer).post(reverse("qa:question-answered", args=[self.first.id]))
        detail = self.client.get(reverse("qa:lecture-detail", args=[DEMO_CODE])).json()
        self.assertEqual(detail["questions"][-1]["id"], self.first.id)

    def test_delete_question_removes_upvotes(self):
        url = reverse("qa:question-detail", args=[self.first.id])
        self.assertEqual(self.as_(self.lecturer).delete(url).status_code, 204)
        self.assertEqual(Upvote.objects.filter(question_id=self.first.id).count(), 0)


# ---------------------------------------------------------------------------
# Docs, seed, tunnel, pages
# ---------------------------------------------------------------------------


class DocsTests(APITestCase):
    def test_schema_covers_every_route_and_declares_jwt(self):
        response = self.client.get(reverse("qa:schema"))
        self.assertEqual(response.status_code, 200)
        spec = response.content.decode()
        for route in (
            "/api/:", "/health/:", "/api/stats/:", "/api/auth/register/:", "/api/auth/login/:", "/api/auth/refresh/:",
            "/api/auth/logout/:", "/api/auth/me/:", "/api/auth/me/password/:", "/api/users/:", "/api/users/{id}/:",
            "/api/lectures/:", "/api/lectures/{key}/:", "/api/lectures/{key}/toggle/:", "/api/lectures/{key}/questions/:",
            "/api/questions/:", "/api/questions/{id}/:", "/api/questions/{id}/upvote/:", "/api/questions/{id}/answered/:",
        ):
            self.assertIn(route, spec)
        self.assertIn("bearerFormat: JWT", spec)

    def test_docs_and_browsable_api_render(self):
        self.assertContains(self.client.get(reverse("qa:docs")), "swagger-ui")
        self.assertContains(self.client.get(reverse("qa:lecture-list"), HTTP_ACCEPT="text/html"), "Lecture List")


class SeedDemoTests(TestCase):
    def test_seed_creates_accounts_and_100_plus_questions_idempotently(self):
        out = StringIO()
        call_command("seed_demo", stdout=out)
        self.assertIn("Seeded 8 lectures", out.getvalue())
        self.assertEqual(User.objects.filter(username__startswith="student", role="student").count(), 41)  # student + student01..40
        self.assertGreaterEqual(Question.objects.count(), 100)
        self.assertGreater(Upvote.objects.count(), 100)
        self.assertTrue(User.objects.get(username="student07").check_password(PASSWORD))
        self.assertTrue(Lecture.objects.filter(code="FLT101", owner__username="lecturer").exists())

        before = (Question.objects.count(), User.objects.count())
        call_command("seed_demo", stdout=StringIO())
        call_command("seed_demo", clear=True, stdout=StringIO())
        self.assertEqual((Question.objects.count(), User.objects.count()), before)

    def test_wait_for_db(self):
        out = StringIO()
        call_command("wait_for_db", attempts=1, stdout=out)
        self.assertIn("Database is up.", out.getvalue())


class TunnelDiscoveryTests(TestCase):
    def setUp(self):
        tunnel.forget_cached_tunnel_url()

    def tearDown(self):
        tunnel.forget_cached_tunnel_url()

    @staticmethod
    def fake_metrics(payload: bytes):
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


class PageTests(TestCase):
    def test_pages_render(self):
        for name in ("qa:home", "qa:login", "qa:register", "qa:cabinet", "qa:users"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        for name in ("qa:lecture", "qa:screen"):
            self.assertEqual(self.client.get(reverse(name, args=[DEMO_CODE])).status_code, 200)
        self.assertEqual(self.client.get(reverse("qa:lecture", args=["NOPE42"])).status_code, 404)

    def test_screen_contains_scalable_qr_with_public_url(self):
        with self.settings(PUBLIC_URL="http://192.168.1.5:8000"):
            response = self.client.get(reverse("qa:screen", args=[DEMO_CODE]))
        self.assertContains(response, "<svg")
        self.assertContains(response, "viewBox=")
        self.assertContains(response, f"http://192.168.1.5:8000/l/{DEMO_CODE}/")
