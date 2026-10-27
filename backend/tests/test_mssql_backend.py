import asyncio

from app.config import Settings, settings
from app.db.mssql import (
    AsyncCursor,
    _apply_update,
    _index_expression,
    _matches,
    _sql_filter,
    build_database_url,
)


def test_document_filter_supports_nested_boolean_and_regex_queries():
    document = {
        "_id": "record-1",
        "status": "pending",
        "employee_id": "EMP001",
        "name": "Alice Supervisor",
    }

    assert _matches(document, {
        "$and": [
            {"status": {"$in": ["pending", "retry"]}},
            {"employee_id": {"$ne": "EMP002"}},
            {"$or": [{"name": {"$regex": "alice", "$options": "i"}}]},
        ],
        "$nor": [{"status": "completed"}],
    })
    assert not _matches(document, {"status": {"$in": ["completed"]}})


def test_scalar_query_compiles_to_parameterized_sql():
    parameters = {}
    where = _sql_filter(
        {
            "employee_id": {"$in": ["EMP001", "EMP002"]},
            "attendance_date": {"$gte": "2026-01-01"},
            "review_status": {"$ne": "superseded"},
        },
        parameters,
    )

    assert where is not None
    assert "IN (:p0, :p1)" in where
    assert parameters == {
        "p0": "EMP001",
        "p1": "EMP002",
        "p2": "2026-01-01",
        "p3": "superseded",
    }
    assert _sql_filter({"name": {"$regex": "Alice", "$options": "i"}}, {}) is None


def test_sparse_unique_submission_ids_are_normalized_for_sql_indexes():
    parameters = {}
    where = _sql_filter(
        {"event_id": "event-123"}, parameters, collection="submissions"
    )

    assert where is not None
    assert "[ixv_" in where
    assert parameters == {"p0": "V:event-123"}


def test_sparse_unique_index_expression_has_balanced_computed_column_parentheses():
    expression = _index_expression("event_id", sparse=True)

    assert expression.startswith("(CONVERT(")
    assert expression.endswith("))")


def test_cursor_supports_projection_and_document_sort_signature():
    class FakeCollection:
        async def _find_documents(self, _query):
            return [
                {"username": "zoe", "role": "viewer"},
                {"username": "amy", "role": "manual_team"},
            ]

    async def collect():
        cursor = AsyncCursor(
            FakeCollection(), {}, {"_id": 0, "username": 1}
        ).sort("username", 1)
        return [item async for item in cursor]

    assert asyncio.run(collect()) == [{"username": "amy"}, {"username": "zoe"}]


def test_update_operators_preserve_document_fields_and_append_history():
    original = {"_id": "row-1", "history": [{"status": "created"}], "attempt": 1}
    changed = _apply_update(original, {
        "$set": {"status": "retry"},
        "$setOnInsert": {"created_at": "now"},
        "$inc": {"attempt": 1},
        "$push": {"history": {"status": "retry"}},
    })

    assert changed == {
        "_id": "row-1",
        "history": [{"status": "created"}, {"status": "retry"}],
        "attempt": 2,
        "status": "retry",
    }


def test_mssql_url_uses_configured_local_database_and_integrated_auth(monkeypatch):
    monkeypatch.setattr(settings, "mssql_server", "localhost")
    monkeypatch.setattr(settings, "mssql_database", "attendance_agent_local")
    monkeypatch.setattr(settings, "mssql_trusted_connection", True)
    url = build_database_url()

    assert url.drivername == "mssql+aioodbc"
    assert url.host == "localhost"
    assert url.database == "attendance_agent_local"
    assert url.username is None
    assert url.password is None
    assert url.query["Trusted_Connection"] == "yes"


def test_db_backend_uses_the_documented_environment_variable(monkeypatch):
    monkeypatch.setenv("DB_BACKEND", "mssql")

    assert Settings(_env_file=None).database_backend == "mssql"
