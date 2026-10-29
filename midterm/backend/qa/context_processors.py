from django.conf import settings


def app_settings(request):
    """Expose a few settings to every template."""
    return {
        "APP_NAME": settings.APP_NAME,
        "REFRESH_SECONDS": settings.REFRESH_SECONDS,
    }
