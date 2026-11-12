# Local Docker stack

Run `deploy\run-local.cmd` from the repository root, then open
http://localhost:8082. Docker Desktop must be running Linux containers.

This creates the separate `attendance-fresh` Compose project with locally built
backend/frontend images, Redis, three workers, and an HTTP gateway bound only to
the local machine. The backend reads SQL connection settings from the ignored
`backend/.env`; Redis settings are set by Compose. The app uses the configured SQL
database, so point it at a dedicated development/test database rather than a live
production database.

Compose build and JWT settings are in the ignored `deploy/.env.docker-local`
file. For a new checkout, create it with a strong random `JWT_SECRET_KEY` and an
`IMAGE_TAG` (for example `local`). SQL and other app settings are in the ignored
`backend/.env`. The current local configuration leaves Interakt credentials empty.
WhatsApp sending and webhooks require separate configuration; the gateway does
not expose a webhook route. Face matching also requires the InsightFace model
weights in the `face-models` volume. This Compose file is for local development,
not production.

Create the first login interactively from the repository root:

```bat
docker compose --env-file deploy/.env.docker-local -f deploy/docker-compose.local.yml exec backend python scripts/create_admin.py
```

Check status or stop the stack (retaining data):

```bat
docker compose --env-file deploy/.env.docker-local -f deploy/docker-compose.local.yml ps
docker compose --env-file deploy/.env.docker-local -f deploy/docker-compose.local.yml stop
```

The health endpoint is http://localhost:8082/api/health.
