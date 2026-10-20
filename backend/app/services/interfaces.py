"""Интерфейсы внешних зависимостей пайплайна (STT, LLM, исполнитель фоновых задач).

Позволяют подменять GigaAM/GigaChat в тестах и при смене модели
(например, Saiga/Vikhr через тот же OpenAI-совместимый llama.cpp сервер).
"""

import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Protocol

from backend.app.schemas.transcription import DomainVocabulary, MeetingTranscription


class Transcriber(Protocol):
    def transcribe(
        self, audio_path: str | Path, vocabulary: DomainVocabulary | None = None
    ) -> MeetingTranscription: ...


class LLMClient(Protocol):
    def health(self) -> None: ...

    def chat(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 512,
        json_schema: dict[str, Any] | None = None,
    ) -> str: ...


class JobRunner(Protocol):
    def submit(self, job: Callable[[], None]) -> None: ...


class ThreadJobRunner:
    """Один рабочий поток: STT и LLM на одном ПК выполняются строго последовательно."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="protocol-job")

    def submit(self, job: Callable[[], None]) -> None:
        self._executor.submit(job)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


class InlineJobRunner:
    """Синхронное выполнение (тесты, отладка)."""

    def submit(self, job: Callable[[], None]) -> None:
        job()


class LLMResponseError(ValueError):
    pass


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_json_object(text: str) -> dict[str, Any]:
    """Извлекает JSON-объект из ответа модели (с учётом ```json-обёрток и текста вокруг)."""
    cleaned = _FENCE_RE.sub("", text.strip())
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise LLMResponseError("Ответ модели не содержит JSON-объекта")
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMResponseError(f"Ответ модели не является корректным JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LLMResponseError("Ответ модели должен быть JSON-объектом")
    return parsed
