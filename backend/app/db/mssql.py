"""SQL Server persistence with the document operations used by the app.

Documents are stored as JSON in one table per logical collection. Indexed
Document fields are materialized as computed columns, so uniqueness and
lookup constraints are enforced by SQL Server rather than process memory.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.db.identifiers import new_record_id, parse_record_id
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.engine import URL

from app.config import settings

logger = logging.getLogger("db")

COLLECTIONS = (
    "roster",
    "coordinators",
    "submissions",
    "counters",
    "face_embeddings",
    "admin_users",
    "webhook_events",
    "notifications",
    "attendance_overrides",
    "admin_state",
)
INDEXED_FIELDS = {
    "roster": {"phone_number", "employee_id", "pc_id"},
    "coordinators": {"pc_id"},
    "submissions": {"employee_id", "attendance_date", "image_hash", "event_id"},
    "face_embeddings": {"employee_id"},
    "admin_users": {"username"},
    "webhook_events": {"event_id"},
    "notifications": {"notification_id", "status"},
    "attendance_overrides": {"employee_id", "attendance_date"},
}
SPARSE_UNIQUE_FIELDS = {("submissions", "event_id")}
_engine: AsyncEngine | None = None
_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def build_database_url() -> URL:
    """Build an async ODBC URL from configuration, never hard-coded secrets."""
    query = {
        "driver": settings.mssql_driver,
        "Encrypt": "yes" if settings.mssql_encrypt else "no",
        "TrustServerCertificate": (
            "yes" if settings.mssql_trust_server_certificate else "no"
        ),
    }
    if settings.mssql_trusted_connection:
        query["Trusted_Connection"] = "yes"
        username = None
        password = None
    else:
        if not settings.mssql_username or not settings.mssql_password:
            raise RuntimeError(
                "MSSQL_USERNAME and MSSQL_PASSWORD are required when "
                "MSSQL_TRUSTED_CONNECTION=false"
            )
        username = settings.mssql_username
        password = settings.mssql_password
    return URL.create(
        "mssql+aioodbc",
        username=username,
        password=password,
        host=settings.mssql_server,
        database=settings.mssql_database,
        query=query,
    )


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(build_database_url(), pool_pre_ping=True)
    return _engine


def _table_name(collection: str) -> str:
    if collection not in COLLECTIONS:
        raise ValueError(f"Unsupported SQL Server collection: {collection}")
    return f"[dbo].[attendance_{collection}]"


def _indexed_column(field: str) -> str:
    return "ixv_" + hashlib.sha1(field.encode()).hexdigest()[:12]


def _json_value_expression(field: str) -> str:
    json_path = "$." + ".".join(field.split("."))
    return (
        f"(CONVERT(nvarchar(400), JSON_VALUE([data_json], '{json_path}') "
        "COLLATE Latin1_General_100_BIN2))"
    )


def _index_expression(field: str, sparse: bool = False) -> str:
    json_path = "$." + ".".join(field.split("."))
    raw = f"JSON_VALUE([data_json], '{json_path}')"
    if sparse:
        return (
            "(CONVERT(nvarchar(400), CASE WHEN "
            f"{raw} IS NULL THEN N'M:' COLLATE Latin1_General_100_BIN2 + [id] "
            f"ELSE N'V:' COLLATE Latin1_General_100_BIN2 + "
            f"{raw} COLLATE Latin1_General_100_BIN2 END "
            "COLLATE Latin1_General_100_BIN2))"
        )
    return _json_value_expression(field)


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Value of type {type(value).__name__} is not JSON serializable")


def _encode(document: dict) -> str:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def _record_id(value: str) -> Any:
    try:
        return parse_record_id(value)
    except Exception:
        return value


def _decode(row: Any) -> dict:
    document = json.loads(row.data_json)
    document["_id"] = _record_id(row.id)
    return document


def _same(left: Any, right: Any) -> bool:
    return left == right


def _field(document: dict, key: str) -> tuple[bool, Any]:
    if key == "_id":
        return ("_id" in document, document.get("_id"))
    current: Any = document
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _condition(value: Any, condition: Any, exists: bool = True, options: str = "") -> bool:
    if not isinstance(condition, dict) or not any(str(k).startswith("$") for k in condition):
        if isinstance(value, list):
            return any(_same(item, condition) for item in value)
        return _same(value, condition)
    for operator, expected in condition.items():
        if operator == "$options":
            continue
        if operator == "$in":
            if not any(
                (_same(item, value) or (isinstance(value, list) and any(_same(item, v) for v in value)))
                for item in expected
            ):
                return False
        elif operator == "$nin":
            if any(_same(item, value) for item in expected):
                return False
        elif operator == "$ne":
            if exists and _same(value, expected):
                return False
        elif operator == "$eq":
            if not _condition(value, expected, exists):
                return False
        elif operator == "$gte":
            if value is None or value < expected:
                return False
        elif operator == "$lte":
            if value is None or value > expected:
                return False
        elif operator == "$gt":
            if value is None or value <= expected:
                return False
        elif operator == "$lt":
            if value is None or value >= expected:
                return False
        elif operator == "$regex":
            if value is None:
                return False
            flags = re.IGNORECASE if "i" in options else 0
            if re.search(str(expected), str(value), flags) is None:
                return False
        elif operator == "$exists":
            if bool(expected) != exists:
                return False
        else:
            raise NotImplementedError(f"Unsupported query operator: {operator}")
    return True


def _matches(document: dict, query: dict | None) -> bool:
    for key, condition in (query or {}).items():
        if key == "$or":
            if not any(_matches(document, child) for child in condition):
                return False
        elif key == "$and":
            if not all(_matches(document, child) for child in condition):
                return False
        elif key == "$nor":
            if any(_matches(document, child) for child in condition):
                return False
        else:
            exists, value = _field(document, key)
            options = condition.get("$options", "") if isinstance(condition, dict) else ""
            if not _condition(value, condition, exists, options):
                return False
    return True


def _sql_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _query_scalar(collection: str | None, field: str, value: Any) -> str:
    scalar = _sql_scalar(value)
    if (collection, field) in SPARSE_UNIQUE_FIELDS:
        return "V:" + scalar
    return scalar


def _sql_filter(
    query: dict | None, params: dict, collection: str | None = None
) -> str | None:
    """Compile the scalar document query subset to SQL Server JSON predicates."""
    clauses = []
    for key, condition in (query or {}).items():
        if key in ("$or", "$and", "$nor"):
            children = [
                _sql_filter(child, params, collection) for child in condition
            ]
            if any(child is None for child in children):
                return None
            joiner = " OR " if key == "$or" else " AND "
            joined = joiner.join(f"({child})" for child in children)
            clauses.append(f"NOT ({joined})" if key == "$nor" else f"({joined})")
            continue
        if not _IDENTIFIER.fullmatch(key.replace(".", "_")) or any(
            not _IDENTIFIER.fullmatch(part) for part in key.split(".")
        ):
            return None
        if key == "_id":
            expr = "[id] COLLATE Latin1_General_100_BIN2"
        else:
            if collection in INDEXED_FIELDS and key in INDEXED_FIELDS[collection]:
                expr = f"[{_indexed_column(key)}]"
            else:
                expr = _json_value_expression(key)
        if isinstance(condition, dict) and any(str(op).startswith("$") for op in condition):
            field_clauses = []
            for op, expected in condition.items():
                if op == "$options":
                    continue
                if op == "$regex":
                    return None
                if op in ("$in", "$nin"):
                    if not expected:
                        field_clauses.append("1=0" if op == "$in" else "1=1")
                    else:
                        names = []
                        for value in expected:
                            name = f"p{len(params)}"
                            params[name] = _query_scalar(collection, key, value)
                            names.append(f":{name}")
                        values = ", ".join(names)
                        clause = f"{expr} IN ({values})"
                        if op == "$nin":
                            clause = f"({expr} IS NULL OR {expr} NOT IN ({values}))"
                            if (collection, key) in SPARSE_UNIQUE_FIELDS:
                                clause = (
                                    f"({expr} LIKE N'M:%' OR "
                                    f"{expr} NOT IN ({values}))"
                                )
                        field_clauses.append(clause)
                elif op in ("$eq", "$ne", "$gt", "$gte", "$lt", "$lte"):
                    if expected is None and op in ("$eq", "$ne"):
                        if (collection, key) in SPARSE_UNIQUE_FIELDS:
                            field_clauses.append(
                                f"{expr} LIKE N'M:%'"
                                if op == "$eq"
                                else f"{expr} NOT LIKE N'M:%'"
                            )
                            continue
                        field_clauses.append(f"{expr} IS {'NOT ' if op == '$ne' else ''}NULL")
                        continue
                    name = f"p{len(params)}"
                    params[name] = _query_scalar(collection, key, expected)
                    operator = {
                        "$eq": "=",
                        "$ne": "<>",
                        "$gt": ">",
                        "$gte": ">=",
                        "$lt": "<",
                        "$lte": "<=",
                    }[op]
                    clause = f"{expr} {operator} :{name}"
                    if op == "$ne":
                        clause = f"({expr} IS NULL OR {clause})"
                    field_clauses.append(clause)
                elif op == "$exists":
                    if (collection, key) in SPARSE_UNIQUE_FIELDS:
                        field_clauses.append(
                            f"{expr} LIKE N'V:%'"
                            if expected
                            else f"{expr} LIKE N'M:%'"
                        )
                        continue
                    field_clauses.append(f"{expr} IS {'NOT ' if expected else ''}NULL")
                else:
                    return None
            clauses.append("(" + " AND ".join(field_clauses or ["1=1"]) + ")")
        else:
            if condition is None:
                if (collection, key) in SPARSE_UNIQUE_FIELDS:
                    clauses.append(f"{expr} LIKE N'M:%'")
                    continue
                clauses.append(f"{expr} IS NULL")
            else:
                name = f"p{len(params)}"
                params[name] = _query_scalar(collection, key, condition)
                clauses.append(f"{expr} = :{name}")
    return " AND ".join(f"({clause})" for clause in clauses) or "1=1"


def _project(document: dict, projection: dict | None) -> dict:
    if not projection:
        return document
    included = [key for key, enabled in projection.items() if enabled]
    if included:
        result = {}
        for key in included:
            exists, value = _field(document, key)
            if exists:
                result[key] = value
        if projection.get("_id", 1) and "_id" in document:
            result.setdefault("_id", document["_id"])
        return result
    return {key: value for key, value in document.items() if not projection.get(key)}


def _sort_value(value: Any) -> tuple[int, Any]:
    if value is None:
        return (0, "")
    return (1, value)


@dataclass
class InsertOneResult:
    inserted_id: Any


@dataclass
class UpdateResult:
    matched_count: int = 0
    modified_count: int = 0
    upserted_id: Any = None


@dataclass
class DeleteResult:
    deleted_count: int = 0


def _apply_update(document: dict, update: dict, inserting: bool = False) -> dict:
    result = dict(document)
    if not any(key.startswith("$") for key in update):
        return {**update, "_id": document.get("_id")}
    for key, fields in update.items():
        if key == "$set" or (key == "$setOnInsert" and inserting):
            result.update(fields)
        elif key == "$inc":
            for field, amount in fields.items():
                result[field] = result.get(field, 0) + amount
        elif key == "$push":
            for field, item in fields.items():
                result[field] = [*(result.get(field) or []), item]
        elif key == "$unset":
            for field in fields:
                result.pop(field, None)
        elif key in ("$setOnInsert",):
            continue
        else:
            raise NotImplementedError(f"Unsupported update operator: {key}")
    return result


class AsyncCursor:
    def __init__(
        self, collection: "Collection", query: dict, projection: dict | None = None
    ):
        self.collection = collection
        self.query = query
        self.projection = projection
        self.offset = 0
        self.limit_value: int | None = None
        self.sort_fields: list[tuple[str, int]] = []
        self._values: list[dict] | None = None
        self._index = 0

    def skip(self, count: int) -> "AsyncCursor":
        self.offset = count
        return self

    def limit(self, count: int) -> "AsyncCursor":
        self.limit_value = count
        return self

    def sort(self, fields: Any, direction: int = 1) -> "AsyncCursor":
        if isinstance(fields, str):
            self.sort_fields = [(fields, direction)]
        else:
            self.sort_fields = list(fields)
        return self

    def __aiter__(self) -> "AsyncCursor":
        self._index = 0
        return self

    async def __anext__(self) -> dict:
        if self._values is None:
            self._values = await self.collection._find_documents(self.query)
            for field, direction in reversed(self.sort_fields):
                self._values.sort(
                    key=lambda doc: _sort_value(_field(doc, field)[1]),
                    reverse=direction < 0,
                )
            end = None if self.limit_value is None else self.offset + self.limit_value
            self._values = self._values[self.offset:end]
        if self._index >= len(self._values):
            raise StopAsyncIteration
        value = self._values[self._index]
        self._index += 1
        return _project(value, self.projection)


class Collection:
    def __init__(self, engine: AsyncEngine, name: str):
        self.engine = engine
        self.name = name
        self.table = _table_name(name)

    async def create_index(self, keys: Any, unique: bool = False, sparse: bool = False):
        if sparse and not unique:
            raise NotImplementedError("Only sparse unique indexes are supported")
        if isinstance(keys, str):
            fields = [(keys, 1)]
        else:
            fields = list(keys)
        column_names = []
        for field, _direction in fields:
            if field == "_id":
                continue
            path_parts = field.split(".")
            if not all(_IDENTIFIER.fullmatch(part) for part in path_parts):
                raise ValueError(f"Unsupported indexed field: {field}")
            column_name = "ixv_" + hashlib.sha1(field.encode()).hexdigest()[:12]
            json_path = "$." + ".".join(path_parts)
            escaped_path = json_path.replace("'", "''")
            expression = _index_expression(
                field, sparse=unique and sparse
            ).replace(f"'{json_path}'", f"'{escaped_path}'")
            async with self.engine.begin() as connection:
                await connection.execute(text(
                    f"IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE "
                    f"object_id = OBJECT_ID('dbo.attendance_{self.name}') "
                    f"AND name = '{column_name}') "
                    f"ALTER TABLE {self.table} ADD [{column_name}] AS "
                    f"{expression} PERSISTED"
                ))
            column_names.append(column_name)
        if not column_names:
            return "_id_"
        signature = "_".join(column_names)
        index_name = "ux_" if unique else "ix_"
        index_name += hashlib.sha1(f"{self.name}:{signature}".encode()).hexdigest()[:16]
        async with self.engine.begin() as connection:
            await connection.execute(text(
                f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = '{index_name}' "
                f"AND object_id = OBJECT_ID('dbo.attendance_{self.name}')) "
                f"CREATE {'UNIQUE ' if unique else ''}INDEX [{index_name}] "
                f"ON {self.table} ({', '.join(f'[{column}]' for column in column_names)})"
            ))
        return index_name

    async def insert_one(self, document: dict) -> InsertOneResult:
        stored = dict(document)
        object_id = stored.get("_id") or new_record_id()
        stored["_id"] = object_id
        await self._insert(stored)
        return InsertOneResult(object_id)

    async def _insert(self, document: dict) -> None:
        object_id = document["_id"]
        async with self.engine.begin() as connection:
            await connection.execute(
                text(f"INSERT INTO {self.table} ([id], [data_json]) VALUES (:id, :body)"),
                {"id": str(object_id), "body": _encode(document)},
            )

    async def _find_documents(self, query: dict | None = None) -> list[dict]:
        params: dict[str, Any] = {}
        where = _sql_filter(query, params, self.name)
        if where is not None:
            async with self.engine.connect() as connection:
                rows = (await connection.execute(
                    text(f"SELECT [id], [data_json] FROM {self.table} WHERE {where}"),
                    params,
                )).all()
            return list(map(_decode, rows))
        async with self.engine.connect() as connection:
            rows = (await connection.execute(
                text(f"SELECT [id], [data_json] FROM {self.table}")
            )).all()
        return [document for document in map(_decode, rows) if _matches(document, query)]

    async def find_one(
        self, query: dict | None = None, projection: dict | None = None, sort: Any = None
    ) -> dict | None:
        values = await self._find_documents(query)
        if sort:
            fields = [(sort, 1)] if isinstance(sort, str) else list(sort)
            for field, direction in reversed(fields):
                values.sort(key=lambda doc: _sort_value(_field(doc, field)[1]), reverse=direction < 0)
        return _project(values[0], projection) if values else None

    def find(
        self, query: dict | None = None, projection: dict | None = None
    ) -> AsyncCursor:
        return AsyncCursor(self, query or {}, projection)

    async def count_documents(self, query: dict | None = None) -> int:
        params: dict[str, Any] = {}
        where = _sql_filter(query, params, self.name)
        if where is not None:
            async with self.engine.connect() as connection:
                return int((await connection.execute(
                    text(f"SELECT COUNT_BIG(*) FROM {self.table} WHERE {where}"),
                    params,
                )).scalar_one())
        return len(await self._find_documents(query))

    async def update_one(self, query: dict, update: dict, upsert: bool = False) -> UpdateResult:
        async with self.engine.begin() as connection:
            await connection.execute(text("EXEC sp_getapplock @Resource=:resource, @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=10000"),
                                     {"resource": f"attendance:{self.name}"})
            rows = (await connection.execute(
                text(f"SELECT [id], [data_json] FROM {self.table} WITH (UPDLOCK, HOLDLOCK)")
            )).all()
            current = next((doc for doc in map(_decode, rows) if _matches(doc, query)), None)
            if current is None:
                if not upsert:
                    return UpdateResult()
                seed = {key: value for key, value in query.items() if not key.startswith("$") and not isinstance(value, dict)}
                current = {"_id": new_record_id(), **seed}
                updated = _apply_update(current, update, inserting=True)
                await connection.execute(
                    text(f"INSERT INTO {self.table} ([id], [data_json]) VALUES (:id, :body)"),
                    {"id": str(updated["_id"]), "body": _encode(updated)},
                )
                return UpdateResult(upserted_id=updated["_id"])
            updated = _apply_update(current, update)
            await connection.execute(
                text(f"UPDATE {self.table} SET [data_json]=:body WHERE [id]=:id"),
                {"id": str(current["_id"]), "body": _encode(updated)},
            )
            return UpdateResult(matched_count=1, modified_count=int(updated != current))

    async def find_one_and_update(
        self, query: dict, update: dict, return_document: Any = False, upsert: bool = False
    ) -> dict | None:
        async with self.engine.begin() as connection:
            await connection.execute(text("EXEC sp_getapplock @Resource=:resource, @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=10000"),
                                     {"resource": f"attendance:{self.name}"})
            rows = (await connection.execute(
                text(f"SELECT [id], [data_json] FROM {self.table} WITH (UPDLOCK, HOLDLOCK)")
            )).all()
            current = next((doc for doc in map(_decode, rows) if _matches(doc, query)), None)
            if current is None:
                if not upsert:
                    return None
                seed = {key: value for key, value in query.items() if not key.startswith("$") and not isinstance(value, dict)}
                current = {"_id": new_record_id(), **seed}
                updated = _apply_update(current, update, inserting=True)
                await connection.execute(
                    text(f"INSERT INTO {self.table} ([id], [data_json]) VALUES (:id, :body)"),
                    {"id": str(updated["_id"]), "body": _encode(updated)},
                )
                return updated
            updated = _apply_update(current, update)
            await connection.execute(
                text(f"UPDATE {self.table} SET [data_json]=:body WHERE [id]=:id"),
                {"id": str(current["_id"]), "body": _encode(updated)},
            )
            return updated if bool(return_document) else current

    async def delete_one(self, query: dict) -> DeleteResult:
        values = await self._find_documents(query)
        if not values:
            return DeleteResult()
        async with self.engine.begin() as connection:
            await connection.execute(
                text(f"DELETE FROM {self.table} WHERE [id]=:id"),
                {"id": str(values[0]["_id"])},
            )
        return DeleteResult(1)

    async def delete_many(self, query: dict) -> DeleteResult:
        values = await self._find_documents(query)
        if not values:
            return DeleteResult()
        async with self.engine.begin() as connection:
            result = await connection.execute(
                text(f"DELETE FROM {self.table} WHERE [id] IN :ids").bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"ids": tuple(str(doc["_id"]) for doc in values)},
            )
        return DeleteResult(len(values))


class Database:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    def __getattr__(self, name: str) -> Collection:
        if name not in COLLECTIONS:
            raise AttributeError(name)
        return Collection(self.engine, name)

    async def command(self, command: str) -> dict:
        if command != "ping":
            raise NotImplementedError(f"Unsupported database command: {command}")
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return {"ok": 1}


def get_db() -> Database:
    return Database(get_engine())


async def delete_attendance_submission_transactional(submission_id: str) -> bool:
    """Delete a photo record and its same-day status override atomically."""
    try:
        object_id = parse_record_id(submission_id)
    except ValueError:
        return False

    engine = get_engine()
    async with engine.begin() as connection:
        row = (await connection.execute(
            text(
                "SELECT [data_json] FROM [dbo].[attendance_submissions] "
                "WITH (UPDLOCK, HOLDLOCK) WHERE [id]=:id"
            ),
            {"id": str(object_id)},
        )).first()
        if row is None:
            return False

        submission = json.loads(row.data_json)
        result = await connection.execute(
            text("DELETE FROM [dbo].[attendance_submissions] WHERE [id]=:id"),
            {"id": str(object_id)},
        )
        if result.rowcount != 1:
            return False

        employee_id = submission.get("employee_id")
        attendance_date = submission.get("attendance_date")
        if not attendance_date:
            from app.db.database import normalize_date_str

            attendance_date = normalize_date_str(submission.get("received_at_utc"))
        if employee_id and attendance_date:
            await connection.execute(
                text(
                    "DELETE FROM [dbo].[attendance_overrides] "
                    "WHERE JSON_VALUE([data_json], '$.employee_id') "
                    "COLLATE Latin1_General_100_BIN2=:employee_id "
                    "AND JSON_VALUE([data_json], '$.attendance_date') "
                    "COLLATE Latin1_General_100_BIN2=:attendance_date"
                ),
                {"employee_id": employee_id, "attendance_date": attendance_date},
            )
        return True


async def ensure_schema() -> None:
    engine = get_engine()
    async with engine.begin() as connection:
        for collection in COLLECTIONS:
            await connection.execute(text(
                f"IF OBJECT_ID('dbo.attendance_{collection}', 'U') IS NULL "
                f"CREATE TABLE [dbo].[attendance_{collection}] ("
                "[id] nvarchar(100) COLLATE Latin1_General_100_BIN2 NOT NULL PRIMARY KEY, "
                "[data_json] nvarchar(max) NOT NULL, "
                "CONSTRAINT [ck_attendance_json_" + collection + "] "
                "CHECK (ISJSON([data_json]) = 1))"
            ))


async def ensure_indexes() -> None:
    await ensure_schema()
    db = get_db()
    await db.roster.create_index("phone_number", unique=True)
    await db.roster.create_index("employee_id", unique=True)
    await db.roster.create_index("pc_id")
    await db.coordinators.create_index("pc_id", unique=True)
    await db.submissions.create_index("employee_id")
    await db.submissions.create_index("attendance_date")
    await db.submissions.create_index([("employee_id", 1), ("attendance_date", 1)])
    await db.submissions.create_index("image_hash")
    await db.face_embeddings.create_index("employee_id", unique=True)
    await db.admin_users.create_index("username", unique=True)
    await db.webhook_events.create_index("event_id", unique=True)
    await db.submissions.create_index("event_id", unique=True, sparse=True)
    await db.notifications.create_index("notification_id", unique=True)
    await db.notifications.create_index("status")
    await db.attendance_overrides.create_index(
        [("employee_id", 1), ("attendance_date", 1)], unique=True
    )


async def close() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
