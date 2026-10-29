"""
`manage.py wait_for_db` — block until the database accepts connections.

entrypoint.sh runs it before `migrate`. Compose already waits for the db
healthcheck, but the very first connection (or the DNS lookup of the service
name) can still fail for a moment on some Docker setups. Retrying with a
one-line reason per attempt is easier to read than a wall of tracebacks.
"""

import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.utils import OperationalError


class Command(BaseCommand):
    help = "Wait until the default database accepts connections."

    def add_arguments(self, parser):
        parser.add_argument("--attempts", type=int, default=30, help="How many times to try (default 30)")
        parser.add_argument("--delay", type=float, default=2.0, help="Seconds between attempts (default 2)")

    def handle(self, *args, **options):
        connection = connections["default"]
        cfg = connection.settings_dict
        target = f"{cfg['USER']}@{cfg['HOST']}:{cfg['PORT']}/{cfg['NAME']}"
        attempts, delay = options["attempts"], options["delay"]
        self.stdout.write(f"Waiting for PostgreSQL at {target} ...")

        for attempt in range(1, attempts + 1):
            try:
                connection.ensure_connection()
            except OperationalError as exc:
                reason = str(exc).strip().splitlines()[0]
                self.stdout.write(f"  attempt {attempt}/{attempts}: {reason}")
                if attempt < attempts:
                    time.sleep(delay)
            else:
                self.stdout.write(self.style.SUCCESS("Database is up."))
                return

        raise CommandError(
            f"Database at {target} is not reachable. Is the db service running on the same "
            "Compose network? Start the whole stack with `docker compose up`, not `docker run`."
        )
