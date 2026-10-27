"""
Central configuration — all tunable values live here.
Per our design decision: thresholds must be adjustable without touching
pipeline logic. Values below are starting defaults, meant to be tuned
after the pilot period against real submission data.
"""

import os
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = os.getenv("ENVIRONMENT", "development")
    # --- Interakt credentials ---
    interakt_api_key: str = os.getenv("INTERAKT_API_KEY", "")
    interakt_webhook_secret: str = os.getenv("INTERAKT_WEBHOOK_SECRET", "")
    interakt_base_url: str = "https://api.interakt.ai/v1/public"

    # --- Admin (for anomaly alerts) ---
    admin_country_code: str = os.getenv("ADMIN_COUNTRY_CODE", "+91")
    admin_phone_number: str = os.getenv(
        "ADMIN_PHONE_NUMBER", ""
    )  # without country code
    admin_session_window_hours: float = (
        24.0  # matches WhatsApp's free-form session rule
    )

    # --- CMS authentication (JWT) ---
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "")  # MUST be set in .env, no safe default
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:5173")

    # --- SQL Server ---
    database_backend: Literal["mssql"] = Field(
        default="mssql", validation_alias="DB_BACKEND",
    )
    mssql_server: str = os.getenv("MSSQL_SERVER", "localhost")
    mssql_database: str = os.getenv("MSSQL_DATABASE", "attendance_agent_local")
    mssql_driver: str = os.getenv("MSSQL_DRIVER", "ODBC Driver 18 for SQL Server")
    mssql_trusted_connection: bool = (
        os.getenv("MSSQL_TRUSTED_CONNECTION", "true").lower() == "true"
    )
    mssql_username: str = os.getenv("MSSQL_USERNAME", "")
    mssql_password: str = os.getenv("MSSQL_PASSWORD", "")
    mssql_encrypt: bool = os.getenv("MSSQL_ENCRYPT", "false").lower() == "true"
    mssql_trust_server_certificate: bool = (
        os.getenv("MSSQL_TRUST_SERVER_CERTIFICATE", "true").lower() == "true"
    )
    app_timezone: str = os.getenv("APP_TIMEZONE", "Asia/Kolkata")

    # --- Redis Streams ---
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_stream_maxlen: int = int(os.getenv("REDIS_STREAM_MAXLEN", "100000"))
    worker_consumer_name: str = os.getenv("WORKER_CONSUMER_NAME", "attendance-worker-1")
    notification_consumer_name: str = os.getenv("NOTIFICATION_CONSUMER_NAME", "notification-worker-1")
    worker_batch_size: int = int(os.getenv("WORKER_BATCH_SIZE", "5"))
    worker_block_ms: int = int(os.getenv("WORKER_BLOCK_MS", "5000"))
    worker_max_retries: int = int(os.getenv("WORKER_MAX_RETRIES", "5"))
    worker_retry_delay_seconds: float = float(os.getenv("WORKER_RETRY_DELAY_SECONDS", "2"))
    notification_max_retries: int = int(os.getenv("NOTIFICATION_MAX_RETRIES", "5"))
    notification_retry_delay_seconds: float = float(os.getenv("NOTIFICATION_RETRY_DELAY_SECONDS", "3"))

    # --- Tunable verification thresholds (Problem 2 from planning) ---
    face_match_pass_threshold: float = 0.70  # >= this => verified match
    face_match_uncertain_threshold: float = (
        0.50  # between this and pass => flag for review
    )
    geofence_radius_meters: float = (
        8000.0  # default attendance range; employees may override it
    )
    shift_window_start: str = (
        "09:00"  # confirmed policy default (with per-employee override)
    )
    shift_window_end: str = "19:00"
    shift_grace_minutes: int = 240

    # --- Duplicate detection ---
    duplicate_hash_hamming_threshold: int = int(
        os.getenv("DUPLICATE_HASH_HAMMING_THRESHOLD", "6")
    )
    normalized_duplicate_hash_hamming_threshold: int = int(
        os.getenv("NORMALIZED_DUPLICATE_HASH_HAMMING_THRESHOLD", "8")
    )

    # --- Passive anti-spoofing / image-quality guard ---
    liveness_enabled: bool = os.getenv("LIVENESS_ENABLED", "true").lower() == "true"
    liveness_min_face_ratio: float = float(os.getenv("LIVENESS_MIN_FACE_RATIO", "0.08"))
    liveness_min_sharpness: float = float(os.getenv("LIVENESS_MIN_SHARPNESS", "35.0"))

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
