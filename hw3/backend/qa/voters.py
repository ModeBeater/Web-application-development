"""
Anonymous voter identity.

There are no accounts yet (authentication arrives in a later homework), so a
voter is a random UUID stored in a cookie. The same UUID decides whether an
upvote toggles on or off. The API also accepts an explicit "voter" value in
the JSON body so the endpoints are easy to try with curl.
"""

import uuid

COOKIE_NAME = "voter"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # one year


def get_voter(request, payload: dict | None = None) -> tuple[str, bool]:
    """Return (voter_id, is_new). Body value wins over the cookie."""
    explicit = (payload or {}).get("voter")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()[:36], False
    existing = request.COOKIES.get(COOKIE_NAME, "")
    if existing:
        return existing[:36], False
    return str(uuid.uuid4()), True


def remember_voter(response, voter_id: str, is_new: bool):
    """Set the cookie on first contact so later votes map to the same voter."""
    if is_new:
        response.set_cookie(
            COOKIE_NAME, voter_id, max_age=COOKIE_MAX_AGE, httponly=True, samesite="Lax"
        )
    return response
