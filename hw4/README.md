# Raise Hand — live questions for lectures

Web Application Development (KBTU, Fall 2026) · **Homework 4 / Endterm · Fullstack Web Application with Authentication**.

Students scan a QR code on the projector, ask questions from their phones and upvote the ones they also have. The most wanted questions float to the top of the screen; the lecturer marks them answered. I teach Flutter at KBTU, so this is a tool for my own lectures.

This is the complete application: the HW3 REST API (Django REST Framework) plus **JWT authentication** (access + refresh tokens with rotation and blacklist), **three roles** (student / lecturer / admin) with permissions on every write, a **React frontend** (Vite + React Router) with protected routes, a **profile page** (username, name, email, password), **user management** — three services (`frontend`, `web`, `db`) running from `docker compose up`.

The final version adds what makes the tool useful after the lecture, not only during it:

* **Topic plan** — a lecture has topics (one-to-many); the lecturer types them in or **uploads the lecture text** (.txt / .md / .pdf, one-to-one with the lecture) and the headings become topics with TF-IDF keywords.
* **Automatic tagging** — when a student asks, a small offline model (`qa/tagging.py`: character n-gram TF-IDF + keyword bonus, scikit-learn) files the question under the right topic, or leaves it untagged when unsure; the student can also pick the topic. Every question carries `tag_source` (`auto` / `manual`) and the model's confidence.
* **“Already asked?”** — while typing, similar existing questions are shown with an upvote button, so duplicates become votes.
* **Written answers** — one per question (one-to-one): the lecturer answers in text, the audience sees it under the question, deleting the question deletes the answer.
* **Summary and export** — questions per topic for the lecturer, Markdown export of the whole lecture (topics → questions → answers) to send to the group.

```text
 browser / phone          frontend (nginx :3000)                 web (Django 5.2 + DRF + SimpleJWT, gunicorn :8000)   db (PostgreSQL 17)
 ───────────────          ─────────────────────────────          ──────────────────────────────────────────────────    ────────────────
 /, /login/, /me/, /l/… ─▶ React build (SPA fallback)                                                                    accounts_user
 /api/auth/*  ───────────▶ proxy ───────────────────────────────▶ accounts/api.py  register · login · refresh · me  ──▶  qa_lecture
 /api/lectures|topics|… ─▶ proxy ───────────────────────────────▶ qa/api.py        viewsets + permissions.py             qa_topic
 /api/users/  ───────────▶ proxy ───────────────────────────────▶ accounts/api.py  admin only                             qa_question
 /docs/, /health/ ───────▶ proxy ───────────────────────────────▶ drf-spectacular, health                                qa_upvote · qa_answer
                                                                  (also published directly on :8000 for Postman)          token_blacklist_*
```

The frontend is a single-page app: React Router renders the pages in the browser and every piece of data comes from the REST API with the JWT the browser holds. nginx serves the build and proxies `/api/…` to the backend over the Compose network, so the app talks to **one origin** (no CORS in production); `django-cors-headers` is configured for the Vite dev server as well.

## Quick start

Requires Docker Desktop (Compose v2). Nothing else is installed on the host.

```bash
cp .env.example .env          # then change POSTGRES_PASSWORD and DJANGO_SECRET_KEY (≥ 32 characters)
docker compose up --build
```

Three containers start: `frontend` (React, <http://localhost:3000>), `web` (API + Swagger, <http://localhost:8000>), `db`. Open **<http://localhost:3000>** and sign in with a demo account (password `Demo12345!`, set by `DEMO_PASSWORD` in `.env`):

| Account | Role | Try |
| --- | --- | --- |
| `admin` | admin | **Users** page: change roles, deactivate, delete; everything below too |
| `lecturer` | lecturer | **Personal cabinet** → My lectures: start a lecture, open the projector **Screen**, close it, mark questions answered |
| `student` (also `aigerim`, `daniyar`, `student01…student40`) | student | **Join** a lecture from a phone: ask, upvote, edit own questions |

| What | URL | Access |
| --- | --- | --- |
| Lectures (search, filters, start a lecture) | <http://localhost:3000/> | public |
| Sign in / Create account | <http://localhost:3000/login/> · <http://localhost:3000/register/> | public |
| **Profile** — personal cabinet: username, name, email, password, my lectures, my questions, tokens | <http://localhost:3000/me/> | **protected** |
| **Topic plan** of a lecture — topics CRUD, material upload, re-tag, summary | <http://localhost:3000/l/FLT107/plan/> | **protected** (changes: owner / admin) |
| Users — roles, activation, deletion | <http://localhost:3000/users/> | **protected, admin** |
| Audience page / projector screen of a lecture | <http://localhost:3000/l/FLT107/> · <http://localhost:3000/l/FLT107/screen/> | public (asking and voting need sign-in) |
| **API docs (Swagger UI with Authorize)** | <http://localhost:8000/docs/> (also <http://localhost:3000/docs/>) | public |
| OpenAPI schema · API root · health | <http://localhost:8000/api/schema/> · <http://localhost:8000/api/> · <http://localhost:8000/health/> | public |

With `SEED_DEMO=1` (default) the first start also creates 40 student accounts and 10 lectures of a Flutter course with lecture material, 30 topics, 126 tagged questions, 14 written answers and ~360 upvotes — **every table has well over 10 rows**.

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

## Frontend (`frontend/`, React 19 + Vite + React Router 7)

A single-page application compiled by Vite and served by nginx (`frontend/Dockerfile`: a Node build stage, then an `nginx:alpine` image with only the static files). No TypeScript, no UI framework — plain React with the same stylesheet the earlier version used, so the code stays readable at a defense.

```text
frontend/src
├── main.jsx, App.jsx            # <BrowserRouter> → routes; public routes vs. routes wrapped in <RequireAuth>
├── api/client.js                # fetch wrapper: Bearer header, 401 → refresh → retry once, DRF error parsing, FormData uploads
├── auth/AuthContext.jsx         # <AuthProvider> + useAuth(): the signed-in user for the whole tree (React Context)
├── auth/RequireAuth.jsx         # route guard: signed in → <Outlet />, otherwise <Navigate to="/login/?next=…" />; optional roles
├── components/Layout.jsx        # header with navigation and the user menu, footer
├── components/Questions.jsx     # question cards: vote, topic chip, answer, lecturer and author tools, topic filter bar
├── components/Toasts.jsx        # notifications
├── hooks.js                     # useLecturePolling (GET /api/lectures/{code}/ every 3 s), useDebounced, useTitle
└── pages/                       # Home, Login, Register, Profile (/me/), Users, Lecture (/l/:code/), Plan (/l/:code/plan/), Screen
```

**Routing and route protection** (`App.jsx`, `auth/RequireAuth.jsx`). Public routes: `/`, `/login/`, `/register/`, `/l/:code/`, `/l/:code/screen/`. Protected routes are nested under a `<Route element={<RequireAuth />}>`: `/me/` (Profile) and `/l/:code/plan/` (topic plan — the REST feature for signed-in users: topics CRUD, material upload, re-tagging, summary); `/users/` is under `<RequireAuth roles={["admin"]} />`. `RequireAuth` reads the session from `useAuth()`: signed in → it renders the child route through `<Outlet />`; signed out → `<Navigate to="/login/?next=/me/" replace />`, and the login page sends the user back to `next` afterwards; wrong role → an explanatory message instead of the page. This is UI-level protection — the API checks every request itself; the frontend only avoids showing pages that would produce 401/403.

**JWT handling** (`api/client.js`, `auth/AuthContext.jsx`). `POST /api/auth/login/` returns `{access, refresh, user}`; the client stores all three in `localStorage` and `AuthProvider` mirrors them into React state, so the header, the menus and the guards re-render on sign-in and sign-out. Every call goes through `api(path, {method, body, auth})`, which adds `Authorization: Bearer <access>`; on a `401` it posts the refresh token to `/api/auth/refresh/`, stores the **new pair** (rotation) and retries the request once; if the refresh is rejected too, the session is cleared and the guards redirect to `/login/`. The Session tab of the profile decodes the access token's payload (`exp`, `user_id`, `role`, `username`) and has a "refresh now" button to show the rotation.

**Errors and loading states.** DRF errors are parsed in one place: `{"detail": …}` becomes a toast (401/403/404/409), `{"field": [...]}` is shown under the matching input (register, profile, password forms); network failures show "Network error". Lists render skeleton tiles / "Loading…" while a request is in flight, submit buttons are disabled while posting, empty states explain what to do next; a 404 lecture code and unknown routes have their own pages.

**Pages.** Lectures list with search, filters (open / closed / mine) and "load more" pagination, plus "Start a lecture" for lecturers; login and register; **Profile** (`/me/`): current user with activity counters, tabs *My lectures* (create, open / close, delete, links to screen / plan), *My questions*, *Profile* (**change username**, first / last name, email — `PATCH /api/auth/me/`), *Security* (**change password** — `POST /api/auth/me/password/`, returns fresh tokens), *Session* (token claims, refresh, sign out); **Users** (admin): table with search and role filter, change role, activate / deactivate, delete; **Lecture** (`/l/:code/`): live board polled every 3 s, ask form with hints from the tagging model while typing ("already asked?" with upvote buttons and the topic the model would pick), manual topic choice, topic filter chips, upvote, edit / delete own questions, lecturer tools on every card (mark answered, write / edit / remove the written answer, change the topic); **Plan** (`/l/:code/plan/`): topics CRUD, material upload (drag-and-drop file or pasted text; headings become topics, questions are re-tagged), re-tag button, per-topic summary, Markdown export; **Screen**: QR code (inline SVG from `GET /api/lectures/{code}/join/`), join code and address, big read-only board, questions-by-topic bars, open / close for the owner. Light / dark theme, responsive down to phone width.

**Development without Docker.** `cd frontend && npm install && npm run dev` starts Vite on <http://localhost:5173> and proxies `/api`, `/docs`, `/health` to `http://127.0.0.1:8000` (`vite.config.js`); set `VITE_API_URL=http://localhost:8000` instead to call the API across origins, which exercises the CORS configuration (`CORS_ALLOWED_ORIGINS`).

## REST API

Reference with examples and the curl walk-through: **[`docs/API.md`](docs/API.md)**. Schema: [`backend/openapi.yaml`](backend/openapi.yaml) (exported from `/api/schema/`).

| Method | Endpoint | Description | Who |
| --- | --- | --- | --- |
| `POST` | `/api/auth/register/` | Create a student or lecturer account → tokens | all |
| `POST` | `/api/auth/login/` | `{username, password}` → `{access, refresh, user}` | all |
| `POST` | `/api/auth/refresh/` | `{refresh}` → new `{access, refresh}` (old refresh revoked) | all |
| `POST` | `/api/auth/logout/` | Revoke a refresh token → 205 | signed in |
| `GET` / `PATCH` | `/api/auth/me/` | My profile with stats / edit **username**, name, email | signed in |
| `POST` | `/api/auth/me/password/` | Change password → fresh tokens | signed in |
| `GET` | `/api/users/` · `/api/users/{id}/` | List / get users (`?role=`, `?is_active=`, `?search=`) | admin |
| `PATCH` / `DELETE` | `/api/users/{id}/` | Change role / active flag · delete | admin |
| `GET` | `/api/lectures/` | List — `?is_open=`, `?owner=me`, `?search=`, `?ordering=`, `?limit=&offset=` | all |
| `POST` | `/api/lectures/` | Create (caller becomes owner) | lecturer, admin |
| `GET` | `/api/lectures/{key}/` | Retrieve by id or code, with topics and questions in screen order | all |
| `PUT` / `PATCH` / `DELETE` | `/api/lectures/{key}/` | Update / delete (cascade: topics, material, questions, upvotes, answers) | owner, admin |
| `POST` | `/api/lectures/{key}/toggle/` | Open / close | owner, admin |
| `GET` / `POST` | `/api/lectures/{key}/questions/` | List / ask (`topic_id` optional → otherwise the model tags it; 409 if closed) | all / signed in |
| `GET` / `POST` | `/api/lectures/{key}/topics/` | Topic plan / add a topic | all / owner, admin |
| `GET` / `POST` / `DELETE` | `/api/lectures/{key}/material/` | Lecture text (JSON or multipart `file`): upload builds topics and re-tags | all / owner, admin |
| `GET` | `/api/lectures/{key}/suggest/?text=` | Preview the automatic tag with a score per topic | all |
| `GET` | `/api/lectures/{key}/similar/?text=` | Similar existing questions ("already asked?") | all |
| `POST` | `/api/lectures/{key}/retag/` | Run the model again over the lecture (`?include_manual=true`) | owner, admin |
| `GET` | `/api/lectures/{key}/join/` | Join address + QR code (inline SVG) for the projector page, where the address came from | all |
| `GET` | `/api/lectures/{key}/summary/` | Totals and questions / answers / votes per topic | all |
| `GET` | `/api/lectures/{key}/export/` | Markdown export (topics → questions → answers) | all |
| `GET` | `/api/topics/` | All topics — `?lecture=`, `?search=`, `?ordering=` | all |
| `GET` / `PUT` / `PATCH` / `DELETE` | `/api/topics/{id}/` | Retrieve / update / delete (questions keep, `topic_id` → null) | all / owner, admin |
| `GET` | `/api/topics/{id}/questions/` | Questions tagged with a topic | all |
| `GET` | `/api/questions/` | List — `?lecture=`, `?topic=`, `?is_answered=`, `?has_answer=`, `?tag_source=`, `?author=me`, `?search=`, `?ordering=` | all |
| `GET` / `PUT` / `PATCH` / `DELETE` | `/api/questions/{id}/` | Retrieve / update (`topic_id` makes the tag manual) / delete | all / author, owner, admin |
| `POST` | `/api/questions/{id}/upvote/` | Toggle the caller's upvote | signed in |
| `POST` | `/api/questions/{id}/answered/` | Toggle answered | owner, admin |
| `GET` / `PUT` / `DELETE` | `/api/questions/{id}/answer/` | Written answer: read / write or replace (201 / 200) / delete | all / owner, admin |
| `GET` | `/api/` · `/api/stats/` · `/health/` · `/api/schema/` | Root, totals, health, OpenAPI | all |

Lists are paginated (`count / next / previous / results`); errors follow DRF (`{"field": [...]}` for 400, `{"detail": "..."}` otherwise).

## Postman collection

[`postman/RaiseHand.postman_collection.json`](postman/RaiseHand.postman_collection.json) — **93 requests, 170 assertions** — plus [`postman/local.postman_environment.json`](postman/local.postman_environment.json) (`baseUrl`, `demoPassword`). Import both, select the environment and run the collection with the Runner: folder **1** registers a throw-away student and lecturer and stores their tokens in collection variables (the collection's default auth is `Bearer {{access_token}}`), shows login, the JWT claims, profile edit, refresh **rotation** and the rejected reuse of the old refresh token; **2–4** run the lecture and question CRUD as the lecturer and the student, including the `401`/`403`/`409` cases; **3b** walks through the final-project features — topics, material upload, the tagging model (auto / manual / untagged), similar questions, answers, summary, export; **5** logs out and proves the refresh token is revoked; **6** signs in as the admin, manages users and deletes the throw-away accounts; **7** shows the error formats and checks the schema. The run is repeatable.

```bash
npx newman run postman/RaiseHand.postman_collection.json -e postman/local.postman_environment.json
# → 93 requests, 170 assertions, 0 failed
```

## Data models

```text
accounts.User (AbstractUser + role: student | lecturer | admin)
   ├── Lecture.owner        (title, code, is_open, created_at)
   │      ├── LectureMaterial (lecture OneToOne CASCADE, title, text, uploaded_by → User)          1 → 1
   │      ├── Topic           (lecture FK CASCADE, title, keywords, description, order)  unique (lecture, title)   1 → N
   │      └── Question        (lecture FK CASCADE, author FK → User, topic FK SET_NULL, tag_source, tag_score,
   │             │             text, is_answered, created_at)                                                      1 → N
   │             ├── Answer   (question OneToOne CASCADE, author FK → User SET_NULL, text, created_at, updated_at)  1 → 1
   │             └── upvoters = ManyToManyField(User, through="Upvote")                                             N ↔ N
   │                    Upvote (question FK CASCADE, user FK CASCADE, created_at)   unique (question, user)
   └── token_blacklist.OutstandingToken / BlacklistedToken  (refresh tokens that can be revoked)
```

* **one-to-one**: `LectureMaterial.lecture`, `Answer.question` (`OneToOneField` = a foreign key with a unique index; `question.answer`, `lecture.material`);
* **one-to-many**: `Lecture.owner`, `Topic.lecture`, `Question.lecture`, `Question.author`, `Question.topic`;
* **many-to-many**: `Question.upvoters` ↔ `User.upvoted_questions` through the explicit `Upvote` table (it carries `created_at` and the uniqueness rule — the `through=` form of `ManyToManyField`).

Everything cascades except `Question.topic` (`SET_NULL`): a topic is a label on the lecture plan, so deleting a topic untags its questions instead of deleting them. Deleting a lecture removes its material, topics, questions, upvotes and answers in one transaction.

Migrations: `accounts/0001` (user), `qa/0001` (schema), `qa/0002` (demo accounts + demo lecture), `qa/0003` (topics, material, answers, tag fields), `qa/0004` (demo topics and an answer for `KBTU26`), `qa/0005` (`upvoters` many-to-many), SimpleJWT's `token_blacklist`. Applied by `entrypoint.sh` on every start.

## Automatic tagging (`backend/qa/tagging.py`, `backend/qa/material.py`)

1. Every topic is a document: title (counted twice), keywords and description — the section of the uploaded lecture text.
2. `TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))` from scikit-learn turns the topics and the new question into vectors; **cosine similarity** gives a score per topic. Character n-grams work across Russian, Kazakh and English, survive typos and word endings, and need no stemmer.
3. Each keyword found in the question adds a bonus (0.25, capped), so the lecturer's own words win.
4. The best topic is used when its score reaches `TAGGING_THRESHOLD` (0.18 by default); otherwise the question stays untagged — a wrong tag is worse than none. The score is stored as `tag_score`, the origin as `tag_source` (`auto` | `manual` | empty).
5. The same vectorizer over the lecture's existing questions powers `/similar/` ("already asked?", `SIMILAR_THRESHOLD` 0.35).

Uploading lecture text (`POST /api/lectures/{key}/material/`) splits it into sections by headings (Markdown `#`, numbered `1.`, ALL CAPS lines, PDF slide titles; paragraph groups as a fallback), extracts the distinguishing words of each section as keywords (word-level TF-IDF across sections) and creates or updates the topics; questions are re-tagged afterwards. `TAGGING_BACKEND=keywords` switches the n-gram part off for comparison. On the demo data the model tags 125 of 126 questions and agrees with a hand-written keyword rule on 48 of the 52 it was checked against.

## Services (compose.yaml)

| Service | Image | Role | Ports | Depends on |
| --- | --- | --- | --- | --- |
| `frontend` | built from `frontend/Dockerfile` (Node build stage → `nginx:1.29-alpine`) | React single-page app; nginx serves the build with an SPA fallback and proxies `/api/`, `/docs/`, `/health/` to `web` | `${FRONTEND_PORT}:80` | `web` |
| `web` | built from `backend/Dockerfile` | Django + DRF (API only) served by gunicorn; migrates, collects the static files of Swagger / the browsable API, seeds | `${WEB_PORT}:8000` | `db` must be **healthy** (`pg_isready`) |
| `db` | `postgres:17-alpine` | PostgreSQL with the named volume `pgdata` | `127.0.0.1:${DB_PORT_HOST}:5432` (host access only, optional) | — |
| `tunnel` (profile `tunnel`, optional) | `cloudflare/cloudflared:2026.10.0` | Public HTTPS address of the frontend for the classroom demo (the QR code follows it automatically) | — | `frontend` |

All services share the `backend` network: nginx reaches the API as `web:8000`, the API reaches the database as `db:5432`; the browser only ever sees `localhost:3000` (and `:8000` for Swagger / Postman). The project is named `raisehand-hw4`, so its containers and volume (`raisehand-hw4_pgdata`) do not collide with the earlier homeworks.

## Configuration (`.env`)

`.env` is git-ignored and excluded from the image; `.env.example` is the committed template. Compose reads it for `${VAR}` interpolation (the `db` service) and passes it to `web` via `env_file:`.

| Variable | Used by | Purpose |
| --- | --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | db, web | Database name, role and password |
| `DJANGO_SECRET_KEY` | web | Django secret key **and** the JWT signing key — required, ≥ 32 characters, no default in code |
| `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | web | Debug flag (default off); allowed hosts (add your LAN IP for a demo) |
| `JWT_ACCESS_MINUTES`, `JWT_REFRESH_DAYS` | web | Token lifetimes (default 15 minutes / 7 days) |
| `TAGGING_BACKEND`, `TAGGING_THRESHOLD`, `SIMILAR_THRESHOLD` | web | Tagging model: `tfidf` (default) or `keywords`; minimum score for an automatic tag (0.18); minimum similarity for "already asked" hints (0.35) |
| `DEMO_PASSWORD` | web | Password of the demo accounts created by the seed (default `Demo12345!`) |
| `SEED_DEMO` | web | `1` loads the demo data set on start (idempotent), `0` keeps only the demo accounts + one lecture |
| `APP_NAME`, `PUBLIC_URL`, `FRONTEND_URL`, `REFRESH_SECONDS` | web | Service name; address for the QR code (empty = tunnel, then `FRONTEND_URL`, then the request address); where the frontend is for the links the API hands out; polling interval reported by `/health/` |
| `CORS_ALLOWED_ORIGINS` | web | Origins allowed to call the API across origins (`django-cors-headers`); the Vite dev server and `localhost:3000` by default |
| `FRONTEND_PORT`, `WEB_PORT`, `DB_PORT_HOST` | compose | Host ports (default 3000 / 8000 / 5433) |

## Commands

```bash
docker compose ps                                   # state and health of the three services
docker compose logs -f web                          # migrations, seed, then gunicorn access log
docker compose logs -f frontend                     # nginx access log (page loads and proxied API calls)
docker compose run --rm web python manage.py test   # 56 tests (auth, permissions, CRUD, relations, topics, tagging, material, answers, docs, seed)
docker compose up -d --build frontend               # rebuild only the React app after a change in frontend/
docker compose exec web python manage.py seed_demo --clear    # regenerate the demo lectures and questions
docker compose exec db psql -U raisehand -d raisehand -c 'SELECT username, role FROM accounts_user LIMIT 10;'
docker compose exec db psql -U raisehand -d raisehand -c 'SELECT count(*) FROM token_blacklist_blacklistedtoken;'
docker compose up -d --build                        # rebuild and recreate after a code change
docker compose down                                 # keep the volume · down -v removes it (fresh database next time)
```

## Roadmap — what would make it a daily tool

Done in this version: topic plan, automatic tagging, "already asked?" hints, written answers, summary and export. Next, in the order I would build them: live updates over WebSocket (Django Channels) instead of polling; a course → lectures hierarchy with an archive and per-course statistics; quick polls ("clear / not clear") during the lecture; a Telegram bot as a second entrance for students; a sentence-embedding backend for tagging (`TAGGING_BACKEND=embeddings`) when the lecture text is long; interface in Russian / Kazakh / English; GitHub Actions running the tests and the Postman collection on every push.

## How the HW4 / endterm requirements are covered

| Requirement | Where |
| --- | --- |
| ≥ 3 entities with one-to-one, one-to-many and many-to-many relationships | 7 models in `backend/qa/models.py` + `accounts/models.py`: `LectureMaterial`–`Lecture` and `Answer`–`Question` (**one-to-one**), `Lecture`→`Topic`/`Question`, `User`→`Lecture`/`Question` (**one-to-many**), `Question.upvoters`↔`User` through `Upvote` (**many-to-many**) — see *Data models* |
| Every table prepopulated with ≥ 10 records | `seed_demo` (runs on start with `SEED_DEMO=1`): 45 users, 10 lectures, 10 materials, 30 topics, 126 questions, 14 answers, ~360 upvotes; the test `test_seed_creates_accounts_and_100_plus_questions_idempotently` asserts ≥ 10 rows per table |
| Full CRUD for the entities | Lectures, topics, questions: list / create / retrieve / update / delete through viewsets; material and answers through `GET`/`POST`/`PUT`/`DELETE` actions; users through `/api/users/` |
| ≥ 1 public GET; `POST`/`PUT`/`PATCH`/`DELETE` require authentication | all `GET`s of lectures / topics / questions / stats / docs are public; every write needs a token (`IsAuthenticatedOrReadOnly` default + object permissions) → `401` without one |
| Signup, login, JWT authentication | `POST /api/auth/register/`, `POST /api/auth/login/`, `/refresh/` (rotation + blacklist), `/logout/` — SimpleJWT, `accounts/api.py` |
| Frontend with ≥ 2 protected routes: Profile + one REST feature for logged-in users | React: `/me/` (Profile) and `/l/:code/plan/` (topic plan: topics CRUD, material upload, re-tag) under `<RequireAuth />`; `/users/` under `<RequireAuth roles={["admin"]} />` |
| Display current user, update username, change password | Profile page: header + counters from `GET /api/auth/me/`; *Profile* tab → `PATCH /api/auth/me/` (`username`, names, email; uniqueness → field error); *Security* tab → `POST /api/auth/me/password/` |
| Handle API errors, loading states, JWT tokens | `frontend/src/api/client.js`: Bearer header, 401 → refresh → retry, error parsing; field errors under inputs, toasts, skeletons / "Loading…", disabled submit buttons |
| Frontend, backend and database as separate Compose services | `compose.yaml`: `frontend` (nginx + React build), `web` (Django API), `db` (PostgreSQL) on the `backend` network, `depends_on` with the database health check |
| Setup instructions in README, Postman collection | this file; `postman/RaiseHand.postman_collection.json` (93 requests) + environment |
| Defense: JWT, protected API endpoints, frontend realization, frontend route protection | *Authentication and authorization*, *Frontend* sections above; `backend/qa/permissions.py`, `frontend/src/auth/RequireAuth.jsx` |
| Earlier requirements kept: filtering / search / pagination, serializers and validation, Docker best practices, env configuration, automatic tagging | `qa/filters.py`, `qa/serializers.py`, `backend/Dockerfile` (non-root, HEALTHCHECK) and `frontend/Dockerfile` (two-stage), `.env`, `qa/tagging.py` |

## Project structure

```text
hw4/
├── compose.yaml, .env.example, .gitignore, README.md
├── docs/API.md                 # endpoint reference, auth walk-through
├── postman/                    # collection (93 requests) + environment
├── frontend/                   # React single-page app (service `frontend`)
│   ├── Dockerfile              # stage 1: node → vite build; stage 2: nginx + dist/
│   ├── nginx.conf              # SPA fallback, /api /docs /health proxied to web:8000
│   ├── package.json, vite.config.js (dev proxy), index.html
│   └── src/
│       ├── main.jsx, App.jsx   # routes: public vs. <RequireAuth> (+ roles)
│       ├── api/client.js       # fetch + JWT (Bearer, refresh on 401, errors)
│       ├── auth/               # AuthContext.jsx (useAuth), RequireAuth.jsx (Navigate / Outlet)
│       ├── components/         # Layout (header, user menu), Questions (cards, tools, filter), Toasts
│       ├── pages/              # Home, Login, Register, Profile, Users, Lecture, Plan, Screen
│       ├── hooks.js, utils.js, app.css
└── backend/                    # Django REST API (service `web`)
    ├── Dockerfile, entrypoint.sh, .dockerignore, requirements.txt, openapi.yaml, manage.py
    ├── config/                 # settings (AUTH_USER_MODEL, REST_FRAMEWORK, SIMPLE_JWT, SPECTACULAR_SETTINGS), urls, wsgi
    ├── accounts/
    │   ├── models.py           # User(AbstractUser) + role, display_name, is_admin / is_lecturer
    │   ├── serializers.py      # register, login (JWT claims), profile, password change, admin user
    │   ├── permissions.py      # IsAdmin, ReadOnly, role helpers
    │   ├── api.py              # /api/auth/* and /api/users/
    │   └── urls.py
    └── qa/
        ├── models.py           # Lecture(owner) → Topic, LectureMaterial; Question(author, topic) → Answer; Question ↔ User through Upvote
        ├── serializers.py      # lecture / topic / material / question / answer shapes with can_manage / can_edit / can_answer
        ├── permissions.py      # LecturePermission, TopicPermission, QuestionPermission
        ├── api.py              # viewsets, actions (topics, material, suggest, similar, retag, join, summary, export, answer), stats, health, root
        ├── tagging.py          # TF-IDF + keyword tagging model, similar questions, re-tagging
        ├── material.py         # lecture text → sections (headings) → topics with keywords; .txt / .md / .pdf
        ├── export.py           # Markdown export of a lecture
        ├── filters.py, pagination.py, lookup.py, links.py, tunnel.py, urls.py
        ├── management/commands/   # wait_for_db.py, seed_demo.py (accounts, material, topics, tagged questions, answers)
        ├── migrations/         # 0001 schema, 0002 demo accounts + lecture, 0003 topics/material/answers, 0004 demo topics, 0005 upvoters M2M
        └── tests.py            # 56 tests
```
