from django.test import SimpleTestCase, override_settings
from django.urls import reverse


class CoreViewsTests(SimpleTestCase):
    """The app has no database, so SimpleTestCase is enough."""

    def test_health_returns_ok(self):
        response = self.client.get(reverse("core:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    @override_settings(APP_GREETING="Hi from the test!", APP_ENV="testing")
    def test_index_shows_values_from_settings(self):
        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hi from the test!")
        self.assertContains(response, "testing")

    @override_settings(APP_GREETING="Hi from the test!", APP_ENV="testing")
    def test_info_returns_json(self):
        data = self.client.get(reverse("core:info")).json()
        self.assertEqual(data["greeting"], "Hi from the test!")
        self.assertEqual(data["environment"], "testing")
        for key in ("debug", "hostname", "python_version", "django_version", "server_time"):
            self.assertIn(key, data)
