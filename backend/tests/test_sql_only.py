import importlib.util
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.db.identifiers import new_record_id, parse_record_id
from app.db.mssql import _decode, _encode, _matches


def test_mssql_is_default_and_other_database_backends_are_rejected(monkeypatch):
    monkeypatch.delenv("DB_BACKEND", raising=False)
    assert Settings(_env_file=None).database_backend == "mssql"
    monkeypatch.setenv("DB_BACKEND", "mongodb")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_existing_sql_ids_survive_serialization_and_document_queries():
    identifier = "68fb12340123456789abcdef"
    document = {"_id": parse_record_id(identifier), "employee_id": "FS001"}
    restored = _decode(SimpleNamespace(id=identifier, data_json=_encode(document)))
    assert restored == document
    assert _matches(restored, {"_id": identifier})
    assert parse_record_id(identifier.upper()) == identifier


def test_generated_sql_ids_use_existing_format_and_are_distinct():
    identifiers = {new_record_id() for _ in range(100)}
    assert len(identifiers) == 100
    assert all(parse_record_id(value) == value for value in identifiers)


@pytest.mark.parametrize("value", ["", "invalid", "a" * 23, "g" * 24, None])
def test_invalid_record_ids_are_rejected(value):
    with pytest.raises(ValueError):
        parse_record_id(value)


def test_legacy_database_module_was_removed():
    assert importlib.util.find_spec("app.db.mongodb") is None
