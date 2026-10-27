# Production deployment with an existing SQL Server

## Server prerequisites

Use a Linux Docker host with Compose v2, a domain and valid TLS certificate,
and network access to the organization's SQL Server and Interakt. This Compose
file does not install SQL Server or create a database. Do not use SQL Server
Developer edition for production.

Have the DBA create a dedicated application database and login. The application
creates its tables and indexes at startup, so the login needs the corresponding
DDL permissions plus read/write access inside that database. Back up any existing
data before switching deployments. This code import does not migrate data from
the testing database or change another application's database.

## Configuration

1. Copy `backend/.env.example` to the ignored `backend/.env`.
2. Set the production `MSSQL_SERVER`, `MSSQL_DATABASE`, `MSSQL_USERNAME`, and
   `MSSQL_PASSWORD`. For a nondefault port use `hostname,port`, as expected by
   the SQL Server ODBC driver. The database must already exist.
3. Set a strong `JWT_SECRET_KEY`, the real `INTERAKT_API_KEY` and
   `INTERAKT_WEBHOOK_SECRET`, admin contact if required, and the exact HTTPS
   dashboard origin in `CORS_ORIGINS`. Never commit the completed env file.
4. Keep `DB_BACKEND=mssql`, `MSSQL_ENCRYPT=true`,
   `MSSQL_TRUST_SERVER_CERTIFICATE=false`. Use a trusted SQL Server certificate
   whose hostname matches the configured server. Install an organization CA in
   the backend image if necessary; do not bypass certificate verification.
5. Replace `example.com` and certificate paths in `deploy/nginx.conf` with the
   real domain. Put the complete certificate tree under `deploy/letsencrypt/`
   (ignored by Git and Docker build context), or adjust the read-only mount to
   the host's certificate directory. Certificates must exist before startup;
   this setup does not issue or renew certificates.

Redis remains internal to the Compose network. The backend and frontend have
no published ports; Nginx serves HTTP redirects and HTTPS on ports 80/443.
There is no MongoDB container, SQL Server test container, or ngrok service.

## Start and verify

If your build network uses an organization HTTPS proxy, provide its trusted
CA as the optional BuildKit secret `build_ca` when building either Dockerfile
(`docker build --secret id=build_ca,src=/path/to/approved-ca.crt ...`). Do not
disable TLS verification. No CA or credential values are stored in this repo.

From the repository root:

```sh
docker compose -f deploy/docker-compose.production.yml config --quiet
docker compose -f deploy/docker-compose.production.yml up --build -d
docker compose -f deploy/docker-compose.production.yml ps
docker compose -f deploy/docker-compose.production.yml logs --tail=100 backend worker absence-worker notification-worker
curl --fail https://YOUR_DOMAIN/api/health
```

The health response must be `{"status":"ok","redis":true,"mssql":true}`
(key order may differ). A running container alone is insufficient. Inspect API
and worker logs, then create the first admin account interactively:

```sh
docker compose -f deploy/docker-compose.production.yml exec backend python scripts/create_admin.py
```

Sign in and verify roster, attendance, exports, and role access. Configure
Interakt's signed POST webhook as `https://YOUR_DOMAIN/webhook/interakt` only
after health and login checks succeed. Test an authorized attendance submission,
worker processing, SQL persistence, and expected notification behavior before
cutover. No live production deployment is performed by transferring this code.

## External dependencies and retained data

Image processing requires InsightFace's `buffalo_l` models. The inherited code
loads/downloads them lazily under the runtime user's `~/.insightface`; provision
the approved models for the deployment and verify inference before cutover.
The Docker image does not bundle those weights. Confirm model licensing for
your intended use. Nominatim reverse geocoding uses
`https://nominatim.openstreetmap.org/reverse`, sends only coordinates, and uses
Redis caching/rate limiting; follow its public usage policy or configure your
own supported `GEOCODING_URL`.

Back up SQL Server through your DBA's backup process. Preserve the `redis-data`
volume for queues. `docker compose ... down` stops services; do not use
`down --volumes` unless intentionally deleting queued jobs. Deploy changes using
`up --build -d` and repeat health, login, and pipeline checks.
