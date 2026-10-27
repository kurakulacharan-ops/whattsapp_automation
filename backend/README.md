# Attendance backend — SQL Server only

The API and all workers use SQL Server through `app/db/database.py` and
`app/db/mssql.py`. The SQL adapter retains JSON document rows and computed
column indexes from the original application. The database must already exist;
startup creates application tables/indexes within the configured database.
There is no alternative database backend.

See the root README and PRODUCTION_DEPLOYMENT.md for configuration and startup.
Copy `.env.example` to the ignored `.env` and set the real SQL connection,
authentication, Redis and Interakt values. Never commit credentials.

Processes: `uvicorn app.main:app`, `python -m app.worker`,
`python -m app.absence_worker`, and `python -m app.notification_worker`.
All must use the same settings and dedicated database/queue instance.

From this directory run `python -m pytest tests -q` after installing
`requirements-test.txt`. `python scripts/test_db_connection.py` performs a
read-only SELECT 1 check against the configured SQL Server. Tests use mocks;
real SQL Server, ODBC, model inference, and webhook checks are required before
production cutover.

Regex searches currently load candidate collections for filtering in Python.
Measure production-size datasets before rollout. Do not run the historical
`migrate_district_assignments.py` for the active city-based location policy.
