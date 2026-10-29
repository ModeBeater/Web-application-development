# Raise Hand — live questions for lectures

Web Application Development (KBTU, Fall 2026) · **Homework 4 / Endterm project: Complete Containerized Web Application**.

Students scan a QR code on the projector, ask questions from their phones and upvote the ones they also have. The most wanted questions float to the top of the screen; the lecturer marks them answered. I teach Flutter at KBTU, so this is a tool for my own lectures.

This is the complete application: the HW3 REST API (Django REST Framework) plus **JWT authentication** (access + refresh tokens with rotation and blacklist), **three roles** (student / lecturer / admin) with permissions on every write, a **personal cabinet**, **user management**, and a **client-side frontend** that talks to the API with the tokens the browser holds — all running from `docker compose up`.

```text
 browser / phone                    web (Django 5.2 + DRF + SimpleJWT + gunicorn)      db (PostgreSQL 17)
 ──────────────────  -p 8000:8000   ───────────────────────────────────────────  db:5432  ──────────────
 pages  /, /login/, /me/, /l/… ──▶  templates + static/qa/app.js (JWT client)            accounts_user
 REST   /api/auth/*  ────────────▶  accounts/api.py   register · login · refresh · me   ─▶ qa_lecture
        /api/lectures|questions ─▶  qa/api.py         viewsets + permissions.py            qa_question
        /api/users/  ────────────▶  accounts/api.py   admin only                            qa_upvote
 docs   /docs/ (Swagger)  ───────▶  drf-spectacular                                         token_blacklist_*
                                                                                             volume: pgdata
```

## Quick start

Requires Docker Desktop (Compose v2). Nothing else is installed on the host.

```bash
cp .env.example .env          # then change POSTGRES_PASSWORD and DJANGO_SECRET_KEY (≥ 32 characters)
docker compose up --build
```

Open <http://localhost:8000> and sign in with a demo account (password `Demo12345!`, set by `DEMO_PASSWORD` in `.env`):

| Account | Role | Try |
| --- | --- | --- |
| `admin` | admin | **Users** page: change roles, deactivate, delete; everything below too |
| `lecturer` | lecturer | **Personal cabinet** → My lectures: start a lecture, open the projector **Screen**, close it, mark questions answered |
| `student` (also `aigerim`, `daniyar`, `student01…student40`) | student | **Join** a lecture from a phone: ask, upvote, edit own questions |

| What | URL |
| --- | --- |
| Lectures (search, filters, start a lecture) | <http://localhost:8000/> |
| Sign in / Create account | <http://localhost:8000/login/> · <http://localhost:8000/register/> |
| Personal cabinet (profile, password, my lectures, my questions, tokens) | <http://localhost:8000/me/> |
| Users (admin) | <http://localhost:8000/users/> |
| Audience page / projector screen of the demo lecture | <http://localhost:8000/l/KBTU26/> · <http://localhost:8000/l/KBTU26/screen/> |
| **API docs (Swagger UI with Authorize)** | <http://localhost:8000/docs/> |
| OpenAPI schema · API root · health | <http://localhost:8000/api/schema/> · <http://localhost:8000/api/> · <http://localhost:8000/health/> |

With `SEED_DEMO=1` (default) the first start also creates 40 student accounts, 8 lectures of a Flutter course, 104 questions and ~330 upvotes, so the lists have 100+ records right away.

## Authentication and authorization

**JWT with `djangorestframework-simplejwt`.** `POST /api/auth/login/` returns an **access token** (15 minutes, sent as `Authorization: Bearer …` with every request; carries `user_id`, `username`, `role`) and a **refresh token** (7 days). When the access token expires the client calls `POST /api/auth/refresh/` and receives a **new pair**: refresh tokens are rotated and the used one is blacklisted (`token_blacklist` app), so a leaked refresh token stops working as soon as the real client refreshes. `POST /api/auth/logout/` blacklists the refresh token explicitly. Registration (`POST /api/auth/register/`) applies Django's password validators and signs the new user in. The profile endpoints (`GET/PATCH /api/auth/me/`, `POST /api/auth/me/password/`) back the personal cabinet.

**Roles** are a column on the custom user model (`accounts.User.role`): `student`, `lecturer`, `admin`. **Permissions** are DRF permission classes applied per viewset (`qa/permissions.py`, `accounts/permissions.py`):

| Action | anonymous | student | lecturer | admin |
| --- | --- | --- | --- | --- |
| Read lectures, questions, stats, docs | ✓ | ✓ | ✓ | ✓ |
| Ask in an open lecture, upvote | — | ✓ | ✓ | ✓ |
| Edit / delete a question | — | own | own + in own lectures | all |
| Create a lecture | — | — | ✓ (owner) | ✓ |
| Rename / open / close / delete a lecture, mark answered | — | — | own | all |
| Manage users (`/api/users/`) | — | — | — | ✓ |

Missing token → `401`, wrong role or not the owner → `403 {"detail": "Only the lecture owner or an admin can do this."}`. Every lecture/question in a response carries `can_manage` / `can_edit` / `can_answer` computed for the caller, so the frontend shows only the controls the user may use.

## Frontend

Server-rendered shells (`backend/qa/templates/qa/*.html`) with a small client in `backend/qa/static/qa/app.js`:

- stores the token pair and the user profile in `localStorage`, adds `Authorization: Bearer` to every API call, and on a `401` silently refreshes the pair and retries once (then signs the user out and redirects to `/login/?next=…`);
- renders DRF errors: `{"detail": …}` as a toast, `{"field": [...]}` under the matching inputs;
- pages: lectures list with search / filters / pagination and "Start a lecture" (lecturers), login, register, personal cabinet (profile, password, my lectures, my questions, session with the access-token expiry and a "refresh now" button), users admin table, audience page (ask, upvote, edit own), projector screen (QR code, live board, close / mark answered for the owner);
- the board polls `GET /api/lectures/{code}/` every `REFRESH_SECONDS`; light / dark theme, responsive down to phone width.

## REST API

Reference with examples and the curl walk-through: **[`docs/API.md`](docs/API.md)**. Schema: [`backend/openapi.yaml`](backend/openapi.yaml) (exported from `/api/schema/`).

| Method | Endpoint | Description | Who |
| --- | --- | --- | --- |
| `POST` | `/api/auth/register/` | Create a student or lecturer account → tokens | all |
| `POST` | `/api/auth/login/` | `{username, password}` → `{access, refresh, user}` | all |
| `POST` | `/api/auth/refresh/` | `{refresh}` → new `{access, refresh}` (old refresh revoked) | all |
| `POST` | `/api/auth/logout/` | Revoke a refresh token → 205 | signed in |
| `GET` / `PATCH` | `/api/auth/me/` | My profile with stats / edit name, email | signed in |
| `POST` | `/api/auth/me/password/` | Change password → fresh tokens | signed in |
| `GET` | `/api/users/` · `/api/users/{id}/` | List / get users (`?role=`, `?is_active=`, `?search=`) | admin |
| `PATCH` / `DELETE` | `/api/users/{id}/` | Change role / active flag · delete | admin |
| `GET` | `/api/lectures/` | List — `?is_open=`, `?owner=me`, `?search=`, `?ordering=`, `?limit=&offset=` | all |
| `POST` | `/api/lectures/` | Create (caller becomes owner) | lecturer, admin |
| `GET` | `/api/lectures/{key}/` | Retrieve by id or code, with questions in screen order | all |
| `PUT` / `PATCH` / `DELETE` | `/api/lectures/{key}/` | Update / delete | owner, admin |
| `POST` | `/api/lectures/{key}/toggle/` | Open / close | owner, admin |
| `GET` / `POST` | `/api/lectures/{key}/questions/` | List / ask (409 if closed) | all / signed in |
| `GET` | `/api/questions/` | List — `?lecture=`, `?is_answered=`, `?author=me`, `?search=`, `?ordering=` | all |
| `GET` / `PUT` / `PATCH` / `DELETE` | `/api/questions/{id}/` | Retrieve / update / delete | all / author, owner, admin |
| `POST` | `/api/questions/{id}/upvote/` | Toggle the caller's upvote | signed in |
| `POST` | `/api/questions/{id}/answered/` | Toggle answered | owner, admin |
| `GET` | `/api/` · `/api/stats/` · `/health/` · `/api/schema/` | Root, totals, health, OpenAPI | all |

Lists are paginated (`count / next / previous / results`); errors follow DRF (`{"field": [...]}` for 400, `{"detail": "..."}` otherwise).

## Postman collection

[`postman/RaiseHand.postman_collection.json`](postman/RaiseHand.postman_collection.json) — **62 requests, 111 assertions** — plus [`postman/local.postman_environment.json`](postman/local.postman_environment.json) (`baseUrl`, `demoPassword`). Import both, select the environment and run the collection with the Runner: folder **1** registers a throw-away student and lecturer and stores their tokens in collection variables (the collection's default auth is `Bearer {{access_token}}`), shows login, the JWT claims, profile edit, refresh **rotation** and the rejected reuse of the old refresh token; **2–4** run the lecture and question CRUD as the lecturer and the student, including the `401`/`403`/`409` cases; **5** logs out and proves the refresh token is revoked; **6** signs in as the admin, manages users and deletes the throw-away accounts; **7** shows the error formats and checks the schema. The run is repeatable.

```bash
npx newman run postman/RaiseHand.postman_collection.json -e postman/local.postman_environment.json
# → 62 requests, 111 assertions, 0 failed
```

## Data models

```text
accounts.User (AbstractUser + role: student | lecturer | admin)
   ├── Lecture.owner      (title, code, is_open, created_at)
   │      └── Question    (lecture FK, author FK → User, text, is_answered, created_at)
   │             └── Upvote (question FK, user FK → User)   unique (question, user)
   └── token_blacklist.OutstandingToken / BlacklistedToken  (refresh tokens that can be revoked)
```

Migrations: `accounts/0001` (user), `qa/0001` (schema), `qa/0002` (demo accounts + demo lecture, data migration), SimpleJWT's `token_blacklist`. Applied by `entrypoint.sh` on every start.

## Services (compose.yaml)

| Service | Image | Role | Ports | Depends on |
| --- | --- | --- | --- | --- |
| `web` | built from `backend/Dockerfile` | Django + DRF served by gunicorn; migrates, collects static files, seeds | `${WEB_PORT}:8000` | `db` must be **healthy** (`pg_isready`) |
| `db` | `postgres:17-alpine` | PostgreSQL with the named volume `pgdata` | `127.0.0.1:${DB_PORT_HOST}:5432` (host access only, optional) | — |
| `tunnel` (profile `tunnel`, optional) | `cloudflare/cloudflared:2026.10.0` | Public HTTPS address for the classroom demo (the QR code follows it automatically) | — | `web` |

Both services share the `backend` network, so the app reaches the database as `db:5432`. The project is named `raisehand-hw4`, so its containers and volume (`raisehand-hw4_pgdata`) do not collide with the earlier homeworks.

## Configuration (`.env`)

`.env` is git-ignored and excluded from the image; `.env.example` is the committed template. Compose reads it for `${VAR}` interpolation (the `db` service) and passes it to `web` via `env_file:`.

| Variable | Used by | Purpose |
| --- | --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | db, web | Database name, role and password |
| `DJANGO_SECRET_KEY` | web | Django secret key **and** the JWT signing key — required, ≥ 32 characters, no default in code |
| `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | web | Debug flag (default off); allowed hosts (add your LAN IP for a demo) |
| `JWT_ACCESS_MINUTES`, `JWT_REFRESH_DAYS` | web | Token lifetimes (default 15 minutes / 7 days) |
| `DEMO_PASSWORD` | web | Password of the demo accounts created by the seed (default `Demo12345!`) |
| `SEED_DEMO` | web | `1` loads the demo data set on start (idempotent), `0` keeps only the demo accounts + one lecture |
| `APP_NAME`, `PUBLIC_URL`, `REFRESH_SECONDS` | web | Header name; address for the QR code (empty = tunnel or request address); polling interval |
| `WEB_PORT`, `DB_PORT_HOST` | compose | Host ports (default 8000 / 5433) |

## Commands

```bash
docker compose ps                                   # state and health of both services
docker compose logs -f web                          # migrations, seed, then gunicorn access log
docker compose run --rm web python manage.py test   # 38 tests (auth, permissions, CRUD, docs, seed, pages)
docker compose exec web python manage.py seed_demo --clear    # regenerate the demo lectures and questions
docker compose exec db psql -U raisehand -d raisehand -c 'SELECT username, role FROM accounts_user LIMIT 10;'
docker compose exec db psql -U raisehand -d raisehand -c 'SELECT count(*) FROM token_blacklist_blacklistedtoken;'
docker compose up -d --build                        # rebuild and recreate after a code change
docker compose down                                 # keep the volume · down -v removes it (fresh database next time)
```

## How the HW4 / endterm requirements are covered

| Requirement | Where |
| --- | --- |
| Extend the REST API into a complete web application | HW3 API + `accounts` app + frontend pages |
| Implement authentication and authorization | SimpleJWT (`accounts/api.py`, `SIMPLE_JWT` in settings): register, login, refresh with rotation + blacklist, logout; roles on `accounts.User` |
| Configure permissions for protected API operations | `qa/permissions.py` (`LecturePermission`, `QuestionPermission`), `accounts/permissions.py` (`IsAdmin`); `IsAuthenticatedOrReadOnly` default |
| Filtering, search, pagination | django-filter (`qa/filters.py`: `is_open`, `owner=me`, `lecture`, `is_answered`, `author=me`), `SearchFilter`, `OrderingFilter`, `LimitOffsetPagination` |
| Integrate the REST API with a client-side frontend | `backend/qa/static/qa/app.js` + templates: all pages read and write through `/api/…` with the Bearer token |
| Handle API requests and errors on the frontend | automatic token refresh on 401, redirect to login, field errors under inputs, toasts for `detail` errors, empty / loading states |
| Backend and database as separate services | `web` and `db` in `compose.yaml`, `backend` network, `depends_on … service_healthy` |
| Containerize with Docker and Docker Compose | `backend/Dockerfile` (non-root user, HEALTHCHECK, entrypoint), `compose.yaml`, named volume `pgdata` |
| Environment variables for configuration and sensitive settings | `.env` → `env_file:` / `${VAR}`; secrets have no defaults in code; `.env` never committed |
| Demonstrate the complete application running through Docker Compose | `docker compose up --build` → <http://localhost:8000> |
| Serializers, CRUD, validation, API client (HW3) | `qa/serializers.py`, viewsets, 38 tests, Postman collection, Swagger |

## Project structure

```text
hw4/
├── compose.yaml, .env.example, .gitignore, README.md
├── docs/API.md                 # endpoint reference, auth walk-through
├── postman/                    # collection (62 requests) + environment
└── backend/
    ├── Dockerfile, entrypoint.sh, .dockerignore, requirements.txt, openapi.yaml, manage.py
    ├── config/                 # settings (AUTH_USER_MODEL, REST_FRAMEWORK, SIMPLE_JWT, SPECTACULAR_SETTINGS), urls, wsgi
    ├── accounts/
    │   ├── models.py           # User(AbstractUser) + role, display_name, is_admin / is_lecturer
    │   ├── serializers.py      # register, login (JWT claims), profile, password change, admin user
    │   ├── permissions.py      # IsAdmin, ReadOnly, role helpers
    │   ├── api.py              # /api/auth/* and /api/users/
    │   └── urls.py
    └── qa/
        ├── models.py           # Lecture(owner) → Question(author) → Upvote(user)
        ├── serializers.py      # lecture / question shapes with can_manage / can_edit / can_answer
        ├── permissions.py      # LecturePermission, QuestionPermission
        ├── api.py              # viewsets, actions, stats, health, root
        ├── filters.py, pagination.py, lookup.py, links.py, tunnel.py, views.py, urls.py
        ├── management/commands/   # wait_for_db.py, seed_demo.py (accounts + 100+ questions)
        ├── migrations/         # 0001 schema, 0002 demo accounts + lecture
        ├── static/qa/          # app.css (design system, light/dark), app.js (JWT client, rendering)
        ├── templates/qa/       # base, home, login, register, cabinet, users, lecture, screen
        └── tests.py            # 38 tests
```
