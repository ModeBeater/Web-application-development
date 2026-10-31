"""API tests — run with `python manage.py test` (or `docker compose exec web python manage.py test`)."""

from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from .models import HuntLog, WantedCriminal


class ApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        # the seed migration (0002) also runs for the test database - start from a clean slate
        HuntLog.objects.all().delete()
        WantedCriminal.objects.all().delete()
        cls.cheap = WantedCriminal.objects.create(
            name="Rhint Celonias", nickname="Rhint", reward=Decimal("800000"), difficulty=2
        )
        cls.armed = WantedCriminal.objects.create(
            name=None, nickname="Ghost", reward=Decimal("9000000"), difficulty=9,
            armed=True, has_crew=True, escape_master=True, latitude=Decimal("-14.2"), longitude=Decimal("44.9"),
        )
        cls.mid = WantedCriminal.objects.create(
            name="Udai Taxim", nickname="Udai", reward=Decimal("3000000"), difficulty=5, armed=True
        )
        cls.hunt = HuntLog.objects.create(criminal=cls.cheap, success=False, notes="first try")
        HuntLog.objects.create(criminal=cls.armed, success=False, notes="escaped")

    # --- criminals -----------------------------------------------------------------------------
    def test_list_criminals(self):
        r = self.client.get("/api/criminals/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([c["id"] for c in r.json()], [self.cheap.id, self.armed.id, self.mid.id])
        self.assertEqual(r.json()[1]["last_known_coordinates"], {"latitude": -14.2, "longitude": 44.9})
        self.assertIsNone(r.json()[0]["last_known_coordinates"])
        self.assertIsNone(r.json()[1]["name"])

    def test_filters_combined_with_sort(self):
        r = self.client.get("/api/criminals/?min_reward=1000000&armed=true&sort=-reward")
        self.assertEqual([c["nickname"] for c in r.json()], ["Ghost", "Udai"])
        r = self.client.get("/api/criminals/?max_reward=3000000&sort=reward")
        self.assertEqual([c["nickname"] for c in r.json()], ["Rhint", "Udai"])
        r = self.client.get("/api/criminals/?has_crew=true&escape_master=true")
        self.assertEqual([c["nickname"] for c in r.json()], ["Ghost"])
        r = self.client.get("/api/criminals/?armed=false")
        self.assertEqual([c["nickname"] for c in r.json()], ["Rhint"])

    def test_invalid_filter_values_are_400(self):
        r = self.client.get("/api/criminals/?min_reward=abc")
        self.assertEqual(r.status_code, 400)
        self.assertIn("min_reward", r.json())
        self.assertEqual(self.client.get("/api/criminals/?armed=maybe").status_code, 400)

    def test_criminal_detail_and_404(self):
        r = self.client.get(f"/api/criminals/{self.armed.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["hunt_count"], 1)
        self.assertEqual(self.client.get("/api/criminals/999/").status_code, 404)
        self.assertEqual(self.client.get("/api/criminals/abc/").status_code, 404)

    def test_criminals_are_read_only(self):
        self.assertEqual(self.client.post("/api/criminals/", {"nickname": "x"}).status_code, 405)
        self.assertEqual(self.client.delete(f"/api/criminals/{self.cheap.id}/").status_code, 405)

    # --- hunt logs ------------------------------------------------------------------------------
    def test_list_hunts_and_filter_by_criminal(self):
        r = self.client.get("/api/hunts/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 2)
        r = self.client.get(f"/api/hunts/?criminal_id={self.cheap.id}")
        self.assertEqual([h["id"] for h in r.json()], [self.hunt.id])
        self.assertEqual(r.json()[0]["criminal_nickname"], "Rhint")
        self.assertEqual(self.client.get("/api/hunts/?criminal_id=abc").status_code, 400)

    def test_create_hunt(self):
        r = self.client.post(
            "/api/hunts/", {"criminal_id": self.mid.id, "success": True, "notes": "  caught  "}, format="json"
        )
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertEqual(body["criminal_id"], self.mid.id)
        self.assertEqual(body["notes"], "caught")
        self.assertTrue(body["created_at"])
        self.assertEqual(HuntLog.objects.count(), 3)

    def test_create_hunt_invalid(self):
        r = self.client.post("/api/hunts/", {"criminal_id": 999, "success": True}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("criminal_id", r.json())
        r = self.client.post("/api/hunts/", {"success": True}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/hunts/", {"criminal_id": self.mid.id, "success": "maybe"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("success", r.json())

    def test_update_and_delete_hunt(self):
        url = f"/api/hunts/{self.hunt.id}/"
        r = self.client.patch(url, {"success": True, "notes": "got him"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()["success"], r.json()["notes"]), (True, "got him"))
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)

    def test_health(self):
        r = self.client.get("/health/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_deleting_criminal_cascades_to_hunts(self):
        self.cheap.delete()
        self.assertFalse(HuntLog.objects.filter(id=self.hunt.id).exists())
