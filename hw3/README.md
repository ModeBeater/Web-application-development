# Raise Hand — live questions for lectures

Web Application Development (KBTU, Fall 2026) · **Homework 3: Django REST API and Database** (Django REST Framework).

Students scan a QR code on the projector, ask questions from their phones and upvote the ones they also have. The most wanted questions float to the top of the screen; the lecturer marks them answered. I teach Flutter at KBTU, so this is a tool for my own lectures.

HW3 takes the midterm application (`midterm/`) and rebuilds its API on **Django REST Framework**: serializers validate and shape the data, viewsets implement the CRUD operations, a router builds the URLs, django-filter / DRF filters add filtering, search and ordering, every list is paginated, and the OpenAPI schema is generated from the code by drf-spectacular. The Docker setup (custom Dockerfile, Compose with PostgreSQL, named volume, `.env`) is unchanged.

```text
 Postman / browser / phone      web (Django 5.2 + DRF + gunicorn)       db (PostgreSQL 17)
 ───────────────────────  -p 8000:8000  ────────────────────────────  db:5432  ────────────
 REST API  /api/...  ───────────────▶  qa/api.py        ViewSets      ─────────▶  qa_lecture
                                        qa/serializers.py validation               qa_question
 Swagger   /docs/    ───────────────▶  drf-spectacular  schema                    qa_upvote
 Browsable API       ───────────────▶  rest_framework   HTML renderer             volume: pgdata
 HTML pages /, /l/<code>/ ──────────▶  qa/views.py + templates
```

## Quick start

Requires Docker Desktop (Compose v2). Nothing else is installed on the host.

```bash
cp .env.example .env          # then change POSTGRES_PASSWORD and DJANGO_SECRET_KEY
docker compose up --build
```

| What | URL |
| --- | --- |
| **API documentation (Swagger UI, "Try it out" works)** | <http://localhost:8000/docs/> |
| OpenAPI 3 schema (generated; `?format=json` for JSON) | <http://localhost:8000/api/schema/> |
| **Browsable API** (DRF renders the endpoints as HTML with forms) | <http://localhost:8000/api/lectures/> |
| API root | <http://localhost:8000/api/> |
| Health check (app + database) | <http://localhost:8000/health/> |
| Lectures list + "Start lecture" | <http://localhost:8000/> |
| Audience page (ask, upvote) | <http://localhost:8000/l/KBTU26/> |
| Projector page (QR code, live board, mark answered) | <http://localhost:8000/l/KBTU26/screen/> |

A demo lecture with code `KBTU26` is created by a data migration on the first start, and with `SEED_DEMO=1` (the default in `.env.example`) the container also loads 8 more lectures with 104 questions and ~270 upvotes, so `GET /api/questions/` returns 100+ records right away.

Stop with `Ctrl+C`, remove the containers with `docker compose down` (the data stays, see below).

## Data models (two related models + upvotes)

```text
Lecture (title, code, is_open, created_at)
   └── Question (lecture FK CASCADE, text, author, is_answered, created_at)
          └── Upvote (question FK CASCADE, voter_id, created_at)   unique (question, voter_id)
```

`backend/qa/models.py`; migrations in `backend/qa/migrations/` (`0001` schema, `0002` demo lecture), applied by `entrypoint.sh` on start.

## REST API (Django REST Framework)

Full reference with examples: **[`docs/API.md`](docs/API.md)**. Machine-readable: [`backend/openapi.yaml`](backend/openapi.yaml) (exported from `/api/schema/`).

| Method | Endpoint | Description | Status |
| --- | --- | --- | --- |
| `GET` | `/api/` | API root: version, links | 200 |
| `GET` | `/health/` | App is up **and** can query the database; Docker `HEALTHCHECK` | 200 / 503 |
| `GET` | `/api/lectures/` | **List** lectures — `?is_open=`, `?search=`, `?ordering=`, `?limit=&offset=` | 200 |
| `POST` | `/api/lectures/` | **Create**: `{"title": "...", "is_open": true}` → join code | 201 |
| `GET` | `/api/lectures/{key}/` | **Retrieve** by id or code, with its questions in screen order | 200 |
| `PUT` / `PATCH` | `/api/lectures/{key}/` | **Update** (full / partial) | 200 |
| `DELETE` | `/api/lectures/{key}/` | **Delete** with its questions and upvotes | 204 |
| `POST` | `/api/lectures/{key}/toggle/` | Open / close the lecture | 200 |
| `GET` | `/api/lectures/{key}/questions/` | **List** the questions of one lecture (paginated) | 200 |
| `POST` | `/api/lectures/{key}/questions/` | **Create** a question: `{"text": "...", "author": "optional"}` | 201 / 409 if closed |
| `GET` | `/api/questions/` | **List** all — `?lecture=`, `?is_answered=`, `?search=`, `?ordering=`, `?limit=&offset=` | 200 |
| `GET` | `/api/questions/{id}/` | **Retrieve** | 200 |
| `PUT` / `PATCH` | `/api/questions/{id}/` | **Update** (`text`, `author`, `is_answered`) | 200 |
| `DELETE` | `/api/questions/{id}/` | **Delete** with its upvotes | 204 |
| `POST` | `/api/questions/{id}/upvote/` | Toggle the caller's upvote (voter = cookie, or `{"voter": "..."}`) | 200 |
| `POST` | `/api/questions/{id}/answered/` | Toggle the answered flag | 200 |

Lists are paginated (`count / next / previous / results`). Errors follow DRF: validation → `{"title": ["Title must be at least 3 characters."]}`, everything else → `{"detail": "..."}` with `404`, `405`, `409`.

```bash
B=http://localhost:8000
curl -s "$B/api/lectures/?search=flutter&ordering=title" | python3 -m json.tool
curl -s -X POST $B/api/lectures/ -H 'Content-Type: application/json' -d '{"title":"Flutter 1 · Lecture 09"}'
curl -s $B/api/lectures/1/                       # same lecture as  $B/api/lectures/KBTU26/
curl -s -X PATCH $B/api/lectures/1/ -H 'Content-Type: application/json' -d '{"is_open":false}'
curl -s -X POST $B/api/lectures/KBTU26/questions/ -H 'Content-Type: application/json' -d '{"text":"Does EXPOSE publish the port?","author":"Yevgeniy"}'
curl -s "$B/api/questions/?ordering=-votes&limit=5"
curl -i -s -X DELETE $B/api/questions/1/         # HTTP/1.1 204 No Content
```

### How a request flows through DRF

`PATCH /api/lectures/5/ {"is_open": false}` → the **router** (`qa/urls.py`) maps the URL to `LectureViewSet.partial_update` → `get_object()` finds the lecture by id or code → `LectureSerializer(instance, data=..., partial=True)` → `is_valid()` runs the field rules (`title` 3–120, `is_open` boolean) and `validate_title()` → `serializer.save()` → `UPDATE qa_lecture …` → the serializer renders the updated row as JSON → `200`. Invalid input never reaches the database: `is_valid(raise_exception=True)` answers `400` with the field errors.

| Piece | File | Role |
| --- | --- | --- |
| Serializers | `backend/qa/serializers.py` | `LectureSerializer`, `LectureDetailSerializer` (nested questions), `QuestionSerializer`; validation (`validate_title`, `validate_text`), read-only vs writable fields, computed fields (`join_url`, `question_count`) |
| ViewSets | `backend/qa/api.py` | `LectureViewSet` (ModelViewSet: list/create/retrieve/update/partial_update/destroy + `toggle`, `questions` actions), `QuestionViewSet` (list/retrieve/update/destroy + `upvote`, `answered`), `health`, `api_root` |
| Router | `backend/qa/urls.py` | `SimpleRouter` turns the viewsets into the URL patterns above |
| Filters | `backend/qa/filters.py` | django-filter `FilterSet`s: `?is_open=`, `?lecture=<id|code>`, `?is_answered=`; DRF `SearchFilter` / `OrderingFilter` for `?search=` / `?ordering=` |
| Pagination | `backend/qa/pagination.py` | `?limit=&offset=` (default 50, max 500) |
| Lookups | `backend/qa/lookup.py` | `find_lecture` (id or code → 404), vote annotations (`Count`, `Exists`) |
| Schema | `config/settings.py` → `SPECTACULAR_SETTINGS` | drf-spectacular generates OpenAPI 3; Swagger UI at `/docs/` |

## Postman collection

[`postman/RaiseHand.postman_collection.json`](postman/RaiseHand.postman_collection.json) (Collection v2.1) — **33 requests with 67 assertions** covering every endpoint, plus [`postman/local.postman_environment.json`](postman/local.postman_environment.json) with `baseUrl = http://localhost:8000`.

Import both (*File → Import*), select the "Raise Hand — local" environment and run the collection with the Collection Runner. The folders tell a story: **1** creates a lecture (its `id`/`code` are stored in collection variables by a test script) → reads it by id and by code → `PUT` → `PATCH` (closes it) → shows the `409` → reopens it; **2** creates a question → lists (paginated, filtered, ordered) → `PUT` → `PATCH` → upvotes twice (toggle) → marks answered → `DELETE` → `404`; **3** deletes the lecture; **4** shows the validation and error responses. Afterwards the database is as before, so the run is repeatable.

```bash
npx newman run postman/RaiseHand.postman_collection.json -e postman/local.postman_environment.json
# → 33 requests, 67 assertions, 0 failed
```

## Services (compose.yaml)

| Service | Image | Role | Ports | Depends on |
| --- | --- | --- | --- | --- |
| `web` | built from `backend/Dockerfile` | Django + DRF served by gunicorn; applies migrations, collects static files on start | `${WEB_PORT}:8000` | `db` must be **healthy** (`pg_isready`) |
| `db` | `postgres:17-alpine` | PostgreSQL with the named volume `pgdata` | `127.0.0.1:${DB_PORT_HOST}:5432` (host access only, optional) | — |
| `tunnel` (profile `tunnel`, optional) | `cloudflare/cloudflared:2026.10.0` | Public HTTPS address for the classroom demo | — | `web` |

Both services share the `backend` network, so the app reaches the database as `db:5432` — the service name is the hostname. The project is named `raisehand-hw3`, so its containers and volume (`raisehand-hw3_pgdata`) do not collide with the earlier homeworks on the same machine.

## Configuration (`.env`)

`.env` is git-ignored and excluded from the image; `.env.example` is the committed template without real credentials. Compose reads `.env` twice: `${VAR}` interpolation inside `compose.yaml` (the `db` service) and `env_file:` for the `web` container.

| Variable | Used by | Purpose |
| --- | --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | db, web | Database name, role and password. The postgres image creates them on the first start; Django connects with the same values |
| `DJANGO_SECRET_KEY` | web | Django secret key (required, no default in code) |
| `DJANGO_DEBUG` | web | `1` enables debug mode (default off) |
| `DJANGO_ALLOWED_HOSTS` | web | Comma-separated hosts; add your LAN IP for a demo |
| `APP_NAME` | web | Name in the page header and API root |
| `PUBLIC_URL` | web | Address other devices use; goes into the QR code. Empty = the tunnel address when the `tunnel` service runs, otherwise the address of the current request |
| `REFRESH_SECONDS` | web | Polling interval of the pages |
| `SEED_DEMO` | web | `1` loads the demo data set on start (idempotent), `0` skips it |
| `WEB_PORT` | compose | Host port for the web service (default 8000) |
| `DB_PORT_HOST` | compose | Host port for PostgreSQL on localhost (default 5433) |

## Demo data, persistence, commands

```bash
docker compose exec web python manage.py seed_demo --clear    # regenerate the 8 demo lectures / 104 questions
docker compose exec db psql -U raisehand -d raisehand -c 'SELECT id, code, title FROM qa_lecture;'
docker compose down        # containers and network removed, volume kept
docker compose down -v     # removes the volume too: the only way to lose the data
docker compose ps                                   # state and health of both services
docker compose logs -f web                          # migrations, then gunicorn access log
docker compose run --rm web python manage.py test   # 35 tests against a temporary PostgreSQL database
docker compose up -d --build                        # rebuild and recreate after a code change
```

`entrypoint.sh` runs on every start: `wait_for_db` → `migrate` → `collectstatic` (CSS/JS of the browsable API, served by WhiteNoise) → `seed_demo` (if `SEED_DEMO=1`) → `exec gunicorn`.

## How the HW3 requirements are covered

| Requirement | Where |
| --- | --- |
| REST API using Django, Django REST Framework and a relational database | `rest_framework` in `INSTALLED_APPS`, PostgreSQL 17 (`db` service) |
| Create and configure a Django project | `backend/config/` — settings read from environment variables |
| At least two related data models | `Lecture` → `Question` → `Upvote` (`backend/qa/models.py`) |
| Create and apply database migrations | `backend/qa/migrations/`, applied by `entrypoint.sh` |
| Django ORM to create, retrieve, update and delete data | `serializer.save()` → INSERT/UPDATE, `instance.delete()`, annotated querysets in `lookup.py` |
| Serializers for application models | `backend/qa/serializers.py` |
| REST API endpoints for CRUD operations | `LectureViewSet`, `QuestionViewSet` (`backend/qa/api.py`) |
| URL routing | `SimpleRouter` in `backend/qa/urls.py` |
| Data validation and appropriate HTTP responses | field rules + `validate_*` in serializers; 200/201/204/400/404/405/409 |
| Test the API using an API client | Postman collection (+ newman), Swagger "Try it out", 35 automated tests |

## Project structure

```text
hw3/
├── compose.yaml            # services (web, db, optional tunnel), network, volume
├── .env.example            # configuration template (copy to .env)
├── docs/API.md             # endpoint reference with examples
├── postman/                # collection (33 requests) + environment
└── backend/
    ├── Dockerfile, entrypoint.sh, .dockerignore, requirements.txt
    ├── openapi.yaml        # generated schema (python manage.py spectacular --file openapi.yaml)
    ├── manage.py
    ├── config/             # settings (REST_FRAMEWORK, SPECTACULAR_SETTINGS), urls, wsgi
    └── qa/
        ├── models.py       # Lecture → Question → Upvote
        ├── serializers.py  # validation + JSON shape
        ├── api.py          # ViewSets, actions, health, root
        ├── urls.py         # router + pages + schema
        ├── filters.py      # django-filter FilterSets
        ├── pagination.py   # limit/offset
        ├── lookup.py       # id-or-code lookup, vote annotations
        ├── links.py        # join_url / screen_url (QR, tunnel)
        ├── views.py        # HTML pages, QR code
        ├── voters.py, tunnel.py, context_processors.py
        ├── management/commands/   # wait_for_db.py, seed_demo.py
        ├── migrations/     # 0001 schema, 0002 demo lecture
        ├── templates/qa/   # base, home, lecture (audience), screen (projector)
        └── tests.py        # 35 tests: CRUD, validation, filters, pagination, schema, seed, tunnel, pages
```
