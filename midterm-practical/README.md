# Space Bounty Hunters — REST API

Midterm practical assignment · Web Application Development (KBTU, Fall 2026) · Nurkhan Tashimov

The same stack as the course projects: **Django 5.2 + Django REST Framework 3.18 + PostgreSQL 17**, running in Docker Compose.
A bounty-hunter guild keeps a database of wanted criminals and a journal of capture attempts (hunt logs).

| Folder / file | What it is |
|---|---|
| [`backend/`](backend/) | Django project (`config/`) and the `bounty` app: models, serializers, filters, viewsets, tests |
| [`backend/bounty/migrations/`](backend/bounty/migrations/) | `0001_initial` — schema; `0002_seed_data` — **demo data (8 criminals, 14 hunt logs)**, applied automatically |
| [`backend/bounty/fixtures/demo_data.json`](backend/bounty/fixtures/demo_data.json) | The same demo data as a Django fixture (`loaddata`) |
| [`db/bounty_data.sql`](db/bounty_data.sql) | The same demo data as a plain SQL dump (`pg_dump --inserts`) |
| [`postman/`](postman/) | Postman collection (28 requests, 60 tests) + environment |
| [`compose.yaml`](compose.yaml), [`.env.example`](.env.example) | Docker Compose: `db` (PostgreSQL) + `web` (gunicorn) |

## 1. Run it

Requirements: Docker Desktop (or Docker Engine + Compose v2).

```bash
git clone https://github.com/ModeBeater/Web-application-development.git
cd Web-application-development
git checkout midterm-practical
cd midterm-practical

cp .env.example .env          # the example values work as they are
docker compose up --build     # first start: builds the image, creates the DB, migrates, seeds demo data
```

Then open **http://localhost:8000/api/** (API root with links) or **http://localhost:8000/api/criminals/**.
Stop with `Ctrl+C`; `docker compose down` removes the containers, `docker compose down -v` also deletes the database volume.

What `docker compose up` does: starts PostgreSQL (`db`, named volume `pgdata`, healthcheck `pg_isready`), waits for it to be healthy, then
`web` runs [`backend/entrypoint.sh`](backend/entrypoint.sh): `wait_for_db` → `migrate` (schema **and** demo data) → `collectstatic` → `gunicorn` on port 8000.

### Without Docker (optional)

```bash
# PostgreSQL must be running; create the database and a user:
#   createdb bounty    (or: psql -c "CREATE DATABASE bounty;")
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export POSTGRES_DB=bounty POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres DB_HOST=127.0.0.1 DB_PORT=5432 \
       DJANGO_SECRET_KEY=any-long-random-string-at-least-32-chars DJANGO_DEBUG=1
python manage.py migrate          # schema + demo data
python manage.py runserver        # http://127.0.0.1:8000/api/
```

## 2. Database setup / import

Nothing to import by hand: migration `0002_seed_data` inserts the demo data the first time `migrate` runs on an empty database
(it is skipped if criminals already exist). The data is also provided in two importable formats:

| Method | Command |
|---|---|
| Migrations (default) | `docker compose up` — or `docker compose exec web python manage.py migrate` |
| Django fixture | `docker compose exec web python manage.py loaddata demo_data` (idempotent: same primary keys) |
| Plain SQL | `docker compose exec -T db psql -U bounty -d bounty < db/bounty_data.sql` (into an **empty** schema — run `migrate` first for the tables) |
| Reset everything | `docker compose down -v && docker compose up --build` |

Connection settings come from `.env` (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`); the database is also reachable from the host
at `localhost:5433` (`DB_PORT_HOST`) for pgAdmin / DBeaver: `psql -h localhost -p 5433 -U bounty -d bounty`.

### Models (`backend/bounty/models.py`)

```
WantedCriminal 1 ──── * HuntLog
```

| `WantedCriminal` | | `HuntLog` | |
|---|---|---|---|
| `id` | PK | `id` | PK |
| `name` | nullable — real name may be unknown | `criminal` | FK → WantedCriminal, `on_delete=CASCADE` |
| `nickname` | required | `success` | bool |
| `reward` | decimal(14,2), the bounty | `notes` | text (may be empty) |
| `latitude`, `longitude` | decimal, optional (last known coordinates) | `created_at` | set by the server (`auto_now_add`) |
| `location_note` | free-text location description | | |
| `difficulty` | 1–10 (validators) | | |
| `armed`, `has_crew`, `escape_master` | bool flags | | |

## 3. API

Base URL `http://localhost:8000`. JSON in and out; lists are plain arrays (no pagination — the dataset is small).

| Method | Path | Purpose | Success | Errors |
|---|---|---|---|---|
| GET | `/api/` | API root with links and examples | 200 | |
| GET | `/health/` | App + DB health (Docker `HEALTHCHECK`) | 200 | 503 DB down |
| GET | `/api/criminals/` | List criminals; filters `min_reward`, `max_reward`, `armed`, `has_crew`, `escape_master` (also `min_difficulty`, `max_difficulty`); `sort=reward` / `sort=-reward` (also `difficulty`, `nickname`, `id`). All combinable. | 200 `[...]` | 400 invalid filter value |
| GET | `/api/criminals/{id}/` | One criminal | 200 | 404 |
| GET | `/api/hunts/` | List hunt logs, newest first; `?criminal_id=5` (also `?success=`) | 200 `[...]` | 400 invalid filter value |
| POST | `/api/hunts/` | Create: `{"criminal_id": 3, "success": false, "notes": "..."}` | 201 | 400 missing / non-existent `criminal_id`, bad boolean, bad JSON |
| GET | `/api/hunts/{id}/` | One hunt log | 200 | 404 |
| PATCH / PUT | `/api/hunts/{id}/` | Update `success`, `notes` (and `criminal_id`) | 200 | 400, 404 |
| DELETE | `/api/hunts/{id}/` | Delete | 204 | 404 |

Criminals are read-only through the API (`POST /api/criminals/` → 405). Error format follows DRF: `{"detail": "..."}` for 404/405/parse
errors, `{"field": ["message"]}` for validation errors.

### Examples

```bash
# armed criminals with a bounty of at least 5 000 000, most expensive first
curl "http://localhost:8000/api/criminals/?min_reward=5000000&armed=true&sort=-reward"
```
```json
[
  {
    "id": 4, "name": "Pierrot Le Fou", "nickname": "Mad Pierrot", "reward": "12000000.00",
    "last_known_coordinates": {"latitude": 25.4, "longitude": 98.7},
    "location_note": "Abandoned theme park outside Mars City",
    "difficulty": 10, "armed": true, "has_crew": false, "escape_master": true, "hunt_count": 2
  },
  { "id": 2, "name": null, "nickname": "Ghost of Ganymede", "reward": "9000000.00", "...": "..." }
]
```

```bash
# the journal of one criminal
curl "http://localhost:8000/api/hunts/?criminal_id=5"

# record an attempt (created_at is set by the server)
curl -X POST http://localhost:8000/api/hunts/ -H "Content-Type: application/json" \
     -d '{"criminal_id": 3, "success": false, "notes": "Lost him near the asteroid belt"}'
# → 201 {"id": 15, "criminal_id": 3, "criminal_nickname": "Teddy", "success": false, "notes": "...", "created_at": "2026-10-31T13:08:56+05:00"}

curl -X PATCH http://localhost:8000/api/hunts/15/ -H "Content-Type: application/json" -d '{"success": true}'   # 200
curl -X DELETE http://localhost:8000/api/hunts/15/                                                               # 204

# invalid requests
curl http://localhost:8000/api/criminals/999/                                   # 404 {"detail": "No WantedCriminal matches the given query."}
curl "http://localhost:8000/api/criminals/?min_reward=abc&armed=maybe"          # 400 {"min_reward": ["Enter a number."], "armed": ["Use true or false."]}
curl -X POST http://localhost:8000/api/hunts/ -H "Content-Type: application/json" -d '{"criminal_id": 999}'   # 400 {"criminal_id": ["Invalid pk \"999\" - object does not exist."]}
```

## 4. Postman

1. Postman → **Import** → drop both files from [`postman/`](postman/):
   `SpaceBountyHunters.postman_collection.json` and `SpaceBountyHunters.local.postman_environment.json`.
2. Select the environment **Space Bounty Hunters — local** (`base_url = http://localhost:8000`).
3. Run the folders in order (or **Run collection**): **1. Criminals** — listing, every filter, sorting, details;
   **2. Hunt logs (CRUD)** — create → read → PATCH → PUT → delete → 404 (chained through the `hunt_id` variable);
   **3. Invalid requests** — 404 for unknown ids, 400 for bad filter values / non-existent `criminal_id` / missing fields / bad booleans, 405 for writing to criminals.

Every request carries tests; the whole collection also runs from the command line:
`npx newman run postman/SpaceBountyHunters.postman_collection.json --env-var base_url=http://localhost:8000`
(28 requests, 60 assertions, 0 failures).

## 5. Tests

```bash
docker compose exec web python manage.py test      # 11 tests: filters, sorting, details, CRUD, validation, 404/405, cascade
```

## How it is built

* `WantedCriminalViewSet` is a `ReadOnlyModelViewSet`; `HuntLogViewSet` is a `ModelViewSet` — DRF's router produces the list/detail
  routes and the correct 405 for unsupported methods.
* Filtering: `django-filter` `FilterSet`s (`bounty/filters.py`) — `NumberFilter(lookup_expr="gte"/"lte")` for the reward range, a strict
  boolean filter that returns 400 for anything other than `true`/`false`; sorting: DRF `OrderingFilter` with `ordering_param = "sort"`.
* `HuntLogSerializer` exposes the FK as `criminal_id` (`PrimaryKeyRelatedField(source="criminal")`), so a non-existent id is a clean 400;
  `created_at` is read-only and set by the database layer.
* Settings are environment-driven (`config/settings.py`), the image runs as a non-root user with a `HEALTHCHECK`, secrets stay in `.env`
  (ignored by git; `.env.example` is committed).
