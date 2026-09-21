# HW1 — Dockerized Django application

Web Application Development (KBTU, Fall 2026) · Homework #1: Docker fundamentals and application containerization.

A minimal Django application served by gunicorn inside a Docker container. The home page shows values that come from environment variables, so configuration changes are visible without rebuilding the image.

## Requirements

- Docker Desktop (or any Docker Engine) — nothing else is needed on the host.

## Build

```bash
docker build -t hw1-web .
```

Optional: build with another Python version (build-time argument):

```bash
docker build --build-arg PYTHON_VERSION=3.12 -t hw1-web:py312 .
```

## Run

```bash
docker run -d --name hw1 -p 8000:8000 hw1-web
```

Open http://localhost:8000

| Endpoint     | Description                          |
| ------------ | ------------------------------------ |
| `/`          | HTML page with runtime information   |
| `/api/info/` | The same information as JSON         |
| `/health/`   | Liveness check used by `HEALTHCHECK` |

### Ports

The application listens on port `8000` inside the container (`EXPOSE 8000`).
`-p HOST:CONTAINER` publishes it on the host, for example on host port 8080:

```bash
docker run -d --name hw1 -p 8080:8000 hw1-web
```

### Environment variables

| Variable               | Default in the image                 | Purpose                          |
| ---------------------- | ------------------------------------ | -------------------------------- |
| `APP_GREETING`         | `Hello from Docker!`                 | Heading on the home page         |
| `APP_ENV`              | `production`                         | Environment label                |
| `DJANGO_DEBUG`         | `0`                                  | `1` enables Django debug mode    |
| `DJANGO_SECRET_KEY`    | development-only fallback            | Django secret key                |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,0.0.0.0,[::1]`  | Comma-separated allowed hosts    |

Override single variables with `-e`:

```bash
docker run -d --name hw1 -p 8000:8000 \
  -e APP_GREETING="Hello, KBTU!" \
  -e APP_ENV=staging \
  hw1-web
```

Or pass a file (`.env` is ignored by git and by Docker builds):

```bash
cp .env.example .env
docker run -d --name hw1 -p 8000:8000 --env-file .env hw1-web
```

## Manage the container

```bash
docker ps                      # running containers (STATUS shows health)
docker logs -f hw1             # application and access logs
docker exec -it hw1 sh         # shell inside the container
docker exec hw1 whoami         # -> appuser (non-root)
docker stop hw1 && docker rm hw1
```

Run the tests inside a throw-away container (overrides the default `CMD`):

```bash
docker run --rm hw1-web python manage.py test
```

## Rebuild after a change

```bash
docker stop hw1 && docker rm hw1
docker build -t hw1-web .
docker run -d --name hw1 -p 8000:8000 hw1-web
```

## Dockerfile highlights

- `python:3.13-slim` — small official base image with a pinned version.
- `requirements.txt` is copied and installed **before** the source code, so code-only changes reuse the cached dependency layer.
- `pip install --no-cache-dir` and `.dockerignore` keep the image and the build context small.
- The app runs as a non-root user (`appuser`).
- `HEALTHCHECK` polls `/health/`; `CMD` uses the exec form so gunicorn receives stop signals.

## Project structure

```text
.
├── Dockerfile
├── .dockerignore
├── .env.example
├── requirements.txt
├── manage.py
├── config/          # Django project (settings read environment variables)
└── core/            # Application: views, urls, template, tests
```
