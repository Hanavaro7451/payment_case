"""Environment-backed application settings."""

import os

DEFAULT_DATABASE_URL = "postgresql+psycopg://kvitto:kvitto@localhost:5432/kvitto"


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_webhook_secret() -> str | None:
    return os.getenv("WEBHOOK_SECRET")
