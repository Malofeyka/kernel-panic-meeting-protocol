"""Настройки бэкенда. Все значения читаются из переменных окружения (.env)."""

import os
from dataclasses import dataclass
from pathlib import Path


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw and raw.strip() else default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw and raw.strip() else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().casefold() in {"1", "true", "yes", "on", "да"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("data")
    max_upload_mb: int = 1024
    max_revision_cycles: int = 2
    llm_chunk_chars: int = 6000
    llm_chunk_overlap_segments: int = 2
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.0
    drop_ungrounded_items: bool = True
    assignee_overload_threshold: int = 5
    organization_name: str = "Министерство образования Свердловской области"
    city: str = "г. Екатеринбург"

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            data_dir=Path(_env_str("DATA_DIR", "data")),
            max_upload_mb=_env_int("MAX_UPLOAD_MB", 1024),
            max_revision_cycles=_env_int("MAX_REVISION_CYCLES", 2),
            llm_chunk_chars=_env_int("LLM_CHUNK_CHARS", 6000),
            llm_chunk_overlap_segments=_env_int("LLM_CHUNK_OVERLAP_SEGMENTS", 2),
            llm_max_tokens=_env_int("LLM_MAX_TOKENS", 2048),
            llm_temperature=_env_float("LLM_TEMPERATURE", 0.0),
            drop_ungrounded_items=_env_bool("DROP_UNGROUNDED_ITEMS", True),
            assignee_overload_threshold=_env_int("ASSIGNEE_OVERLOAD_THRESHOLD", 5),
            organization_name=_env_str(
                "ORGANIZATION_NAME", "Министерство образования Свердловской области"
            ),
            city=_env_str("ORGANIZATION_CITY", "г. Екатеринбург"),
        )
