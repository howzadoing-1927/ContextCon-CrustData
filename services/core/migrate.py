"""Render and apply db/migrations/*.sql for the configured schema and evidence bucket.

    python -m services.core.migrate            # apply every migration in order (each refuses to re-apply)
    python -m services.core.migrate --print    # print rendered SQL only (for the Supabase SQL editor)
"""

import argparse
import sys
from pathlib import Path

import psycopg

from .config import REPO_ROOT, Settings, get_settings
from .db import connect_kwargs

MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"


def render(path: Path, settings: Settings) -> str:
    return (
        path.read_text()
        .replace("__OUTCOME_PRIVATE_SCHEMA__", settings.private_schema)
        .replace("__OUTCOME_SCHEMA__", settings.db_schema)
        .replace("__EVIDENCE_BUCKET__", settings.storage_bucket)
    )


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m services.core.migrate")
    parser.add_argument("--print", action="store_true", dest="print_only")
    args = parser.parse_args(argv)
    settings = get_settings()

    rendered = [(path.name, render(path, settings)) for path in migration_files()]
    if args.print_only:
        for name, text in rendered:
            sys.stdout.write(f"-- ===== {name} (schema={settings.db_schema}, bucket={settings.storage_bucket})\n{text}\n")
        return
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set")
    with psycopg.connect(settings.database_url, **connect_kwargs()) as conn:
        for name, text in rendered:
            conn.execute(text)
            print(f"applied {name} to schema {settings.db_schema} (bucket {settings.storage_bucket})")


if __name__ == "__main__":
    main()
