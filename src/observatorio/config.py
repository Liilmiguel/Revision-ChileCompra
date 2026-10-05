"""Configuración desde el entorno, con .env opcional en la raíz del repo."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_URL = "postgresql://observatorio:observatorio@localhost:5432/observatorio"


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.strip().startswith("#") and value.strip():
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def ticket() -> str:
    value = os.environ.get("MERCADO_PUBLICO_TICKET", "")
    if not value:
        raise SystemExit("Falta MERCADO_PUBLICO_TICKET (en .env o en el entorno).")
    return value


def raw_dir() -> Path:
    return Path(os.environ.get("OBSERVATORIO_RAW_DIR", ROOT / "data" / "raw"))
