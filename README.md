# Attendance — MSSQL deployment

One FastAPI backend, one React frontend, SQL Server persistence, and Redis job
queues. Application code is consolidated from `holmes24/mssql` commit
`573d3c09193a7803e53c7a87dc5cd6879a9fb816`: the root `backend/` and
`frontend/`, with every file from the `attendance_dev` backend/frontend applied
over the corresponding root files, as its Dockerfiles did. The database layer is then consolidated for MSSQL-only use.

There is one application tree and MSSQL is the only supported database backend.
Shared database functions live in `backend/app/db/database.py`; persistence is
implemented by `app/db/mssql.py`. MongoDB clients, fallback configuration,
Motor, PyMongo, and BSON dependencies have been removed. SQL Server retains the
source's JSON document tables and existing 24-hex record IDs.

The consolidated version retains direct coordinator reporting, attendance and
roster exports, optional override reasons, English/Hindi/Marathi OCR, role shift
defaults, the FS location toggle, range/city location policy, and notification
filtering. Production sets the testing stack's 7% face-size threshold explicitly.
Automatic legacy hierarchy migration only runs in the source's `testing` mode;
production does not automatically migrate existing roster data.

See [production deployment](PRODUCTION_DEPLOYMENT.md) for server configuration.
For a Windows source checkout, keep application secrets in
`deploy\runtime.env`, configure the HTTPS gateway, and run
`deploy\run-from-source.cmd` to build and start Docker containers. The source
build route does not require GHCR login. Published-image deployment remains
available through the GitHub Actions artifact.
No databases, credentials, employee records, or source repository history are
copied by this import.

## Development and checks

Use Python 3.12, Node.js 22+, Microsoft ODBC Driver 18, Redis 8, and Tesseract
with `eng`, `hin`, and `mar` language data. From the repository root:

```sh
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements-test.txt
cd frontend
npm ci
npm run build
npm run lint
cd ../backend
DB_BACKEND=mssql LIVENESS_MIN_FACE_RATIO=0.07 .venv/bin/python -m pytest tests
```

Configure an ignored `backend/.env` for a dedicated development SQL database
and Redis before starting the API. Use `ENVIRONMENT=development` and
`CORS_ORIGINS=http://localhost:5174` locally. The inherited Vite configuration
uses port 5174 and proxies `/api` to port 8001:

```sh
cd backend
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
# In another terminal, from frontend/:
npm run dev
```

Run `python -m app.worker`, `python -m app.absence_worker`, and
`python -m app.notification_worker` from `backend/` with the same virtual
environment and settings when testing the complete pipeline. Live Interakt
credentials can send real messages; use a separate test account/database.

Unit tests exercise application logic and SQL generation with mocks; they do
not establish connectivity to a live SQL Server or validate model inference.
