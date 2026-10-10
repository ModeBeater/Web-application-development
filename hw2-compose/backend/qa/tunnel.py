"""
Discover the public address of the optional `tunnel` service (cloudflared quick tunnel).

cloudflared publishes the random *.trycloudflare.com hostname on its metrics
server: GET /quicktunnel -> {"hostname": "..."}. The web container asks for it
over the Compose network, so the QR code points to the tunnel automatically
while it is running, with no manual copy-paste of the address.

The lookup is cached: the pages poll the API every few seconds and must not
hit cloudflared on every request. A failed lookup (tunnel not started) is
cached too, for a shorter time.
"""

import json
import time
import urllib.request

from django.conf import settings

CACHE_OK_SECONDS = 60
CACHE_FAIL_SECONDS = 15
TIMEOUT_SECONDS = 0.7

_cache = {"until": 0.0, "url": ""}


def tunnel_public_url() -> str:
    """Return 'https://<hostname>' of the running tunnel, or '' if there is none."""
    now = time.monotonic()
    if now < _cache["until"]:
        return _cache["url"]

    url = ""
    base = settings.TUNNEL_METRICS_URL.rstrip("/")
    if base:
        try:
            with urllib.request.urlopen(f"{base}/quicktunnel", timeout=TIMEOUT_SECONDS) as response:
                hostname = json.load(response).get("hostname", "")
            if hostname:
                url = f"https://{hostname}"
        except Exception:  # noqa: BLE001 - tunnel not running, DNS failure, timeout: all mean "no tunnel"
            url = ""

    _cache["until"] = now + (CACHE_OK_SECONDS if url else CACHE_FAIL_SECONDS)
    _cache["url"] = url
    return url


def forget_cached_tunnel_url():
    """Used by tests."""
    _cache["until"] = 0.0
    _cache["url"] = ""
