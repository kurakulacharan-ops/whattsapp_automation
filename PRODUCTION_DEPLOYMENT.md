# Deploy published Docker images from GHCR

## Alternative: build from a checkout on the Windows Docker host

If the server should pull approved source and build its own images, use this
route instead of downloading a GHCR deployment bundle. The Docker engine must
run Linux containers. The Windows Server support guidance below still applies.

For example, clone the repository to `C:\attendance\whattsapp_automation`.
For an existing checkout, fetch and check out the approved commit before building;
do not discard local changes or secret files. Put your existing application
`.env` at **`C:\attendance\whattsapp_automation\deploy\runtime.env`**.
The filename must be `runtime.env`, not `runtime.env.txt`. This is the file all
backend processes read. It is ignored by Git and excluded from Docker images.
No application secrets belong in `deploy/build.env.example` or `deploy/.env`.

If you do not already have an application env file, initialize one without
overwriting an existing file. From the repository root in Command Prompt:

```bat
if not exist deploy\runtime.env copy deploy\runtime.env.example deploy\runtime.env
notepad deploy\runtime.env
```

Set the real SQL connection, JWT and Interakt values described under Server
configuration below. If SQL Server runs directly on the same Windows machine,
Docker Desktop containers usually reach it through `host.docker.internal`,
with the configured SQL TCP port. Use a hostname matching the SQL TLS certificate
and reachable from the containers; keep certificate verification enabled.
`localhost` inside a container refers to that container, not the Windows host.

Configure `deploy/nginx.conf` with the production domain and supply its TLS
certificates under `deploy/letsencrypt/` before starting the HTTPS gateway.
Then run from the repository root:

```bat
deploy\run-from-source.cmd
docker compose --env-file deploy\build.env.example -f deploy\docker-compose.production.yml -f deploy\docker-compose.build.yml ps
```

The script builds `attendance-backend:local` and `attendance-frontend:local` and
starts the application with the existing SQL Server and internal Redis. It
returns a failing exit code if validation, build or readiness fails. No GHCR
login is needed for these locally built application images. For distinct local
release tags, set `IMAGE_TAG` to the approved commit in the invoking shell before
running the script. Repeat the health, login and pipeline checks below after
startup. The rest of this document describes the image-publishing alternative.

GitHub Actions builds and tests the application on pushes to `main`. After both
images build and the backend tests pass, it publishes a matched pair:

- `ghcr.io/kurakulacharan-ops/whattsapp_automation-backend:sha-<full-commit>`
- `ghcr.io/kurakulacharan-ops/whattsapp_automation-frontend:sha-<full-commit>`

Pull requests build/test without publishing. The workflow uses GitHub's built-in
`GITHUB_TOKEN` with package-write permission; production credentials are never
required by Actions. Enable Actions for this repository and permit package
publishing in your organization settings. The workflow does not log in to or
change your server.

## Check the Windows host

These images are `linux/amd64`. On Windows Server, run them in a supported Linux
VM (for example under Hyper-V). Docker Desktop is intended for supported Windows
10/11 editions and is not supported on Windows Server. Run the included
`inspect-server.ps1` in PowerShell for a read-only OS, Docker, SSH and VM report.
On the actual container host, `docker info --format '{{.OSType}}'` must say
`linux`, and `docker compose version` must work. The host needs SQL Server network
access, HTTPS access to GHCR and Interakt, and inbound HTTPS for the application.

## Get the deployment bundle

Open GitHub **Actions → Build and publish Docker images → successful run**.
Download `attendance-deployment-<commit>` from Artifacts and extract it into a
server directory such as `/opt/attendance` in the Linux VM. It contains only:

- `compose.yml` — pulls images; contains no build steps or source mounts.
- `.env` — the published image prefix and exact matching commit tag; no secrets.
- `runtime.env.example` — template for server-only application secrets/settings.
- `nginx.conf`, `inspect-server.ps1`, and this README.

Keep this directory, `runtime.env`, certificate files, and Docker volumes across
updates. Do not replace an existing `runtime.env` with a template. If the artifact
has expired, rerun the workflow for the chosen commit to regenerate it. For a
manual deployment-file checkout, copy `deploy/docker-compose.production.yml` to
`compose.yml` and `deploy/.env.example` to `.env`, then set the published tag.
The server does not need the application source or a Git clone.

## Server configuration

1. Copy `runtime.env.example` to `runtime.env` only on first installation. Restrict
   access to the deployment account (for Linux: `chmod 600 runtime.env`). Keep
   this file outside source control and never upload it to Actions.
2. Have your DBA create a dedicated application database and login. Set
   `MSSQL_SERVER`, `MSSQL_DATABASE`, `MSSQL_USERNAME`, and `MSSQL_PASSWORD` in
   `runtime.env`. Use `hostname,port` for a nondefault port. The application
   creates tables/indexes in that database and needs corresponding DDL and DML
   rights. It does not create the production database or migrate testing data.
3. Keep `DB_BACKEND=mssql`, `MSSQL_ENCRYPT=true`, and
   `MSSQL_TRUST_SERVER_CERTIFICATE=false`. Use a SQL certificate trusted by the
   backend image and matching the hostname. If your organization uses a private
   CA, provision its public certificate through an approved image build; never
   disable verification. A Linux VM reaches a Windows-hosted SQL instance using
   the Windows machine's reachable hostname/IP, not `localhost`.
4. Set a strong `JWT_SECRET_KEY`, real `INTERAKT_API_KEY` and
   `INTERAKT_WEBHOOK_SECRET`, the exact HTTPS dashboard origin in `CORS_ORIGINS`,
   and any required admin contact. `runtime.env` is Compose env-file syntax:
   single-quote values containing `$` to prevent interpolation. Treat the file
   as data; do not source it as a shell script.
5. Replace `example.com` and certificate paths in `nginx.conf`. Put the complete
   TLS certificate tree under `letsencrypt/`, or adjust the read-only mount to
   your existing certificate directory. Certificates must exist before startup;
   renewal remains your server's responsibility.

If images are private, log in on the container host with an account granted
access to both packages. A classic PAT with `read:packages` (and organization SSO
approval when required) can be entered at Docker's password prompt:

```sh
docker login ghcr.io -u YOUR_GITHUB_USERNAME
```

Do not pass the token as a command-line password or put it in Compose. Confirm
package access in GitHub if `pull` returns denied; changing the image tag does
not fix permissions.

## Start, verify, and update

Run from the extracted deployment directory (these Docker commands also work
in PowerShell when it targets a supported Linux Docker engine):

```sh
docker compose --env-file .env -f compose.yml config --quiet
docker compose --env-file .env -f compose.yml pull
docker compose --env-file .env -f compose.yml up -d --no-build --wait --wait-timeout 180
docker compose --env-file .env -f compose.yml ps
docker compose --env-file .env -f compose.yml logs --tail=100 backend worker absence-worker notification-worker
curl --fail https://YOUR_DOMAIN/api/health
```

Health must report `{"status":"ok","redis":true,"mssql":true}`. The API and
all workers use MSSQL. Redis is internal; only Nginx publishes ports 80/443.
Create the initial admin interactively on first installation:

```sh
docker compose --env-file .env -f compose.yml exec backend python scripts/create_admin.py
```

Verify login, roster operations, exports, worker processing and SQL persistence.
Provision approved InsightFace `buffalo_l` weights into the shared `face-models`
volume and verify face inference before accepting real photo submissions.
Weights are not bundled in the images. Confirm their license for the intended
use. Configure the signed Interakt webhook to
`https://YOUR_DOMAIN/webhook/interakt` after those checks, and test notifications
with an authorized test account. Nominatim geocoding sends coordinates only and
uses Redis caching/rate limiting; follow its usage policy or set a supported
`GEOCODING_URL`.

For an update, back up SQL Server, retain the previous `.env` image tag, and
replace only `.env` with the version from a successful Actions artifact (review
any deployment configuration changes separately). Run `pull` and `up` again.
Both application images use the same commit tag. To roll back application code,
restore the previous tag and repeat `pull` and `up`; a code rollback does not
reverse database/schema changes, so use the DBA's recovery plan where necessary.
Never use `down --volumes` for an ordinary update: it deletes queued jobs and
cached face models. Keep SQL Server backups under your organization's process.
