"""Сборка сервисов приложения (DI). В тестах подменяется через `set_services`."""

import threading
from collections.abc import Callable
from dataclasses import dataclass

from dotenv import load_dotenv

from backend.app.core.config import Settings
from backend.app.persistence.session_store import SessionStore
from backend.app.services.docx_generator import DocxGenerator
from backend.app.services.interfaces import JobRunner, LLMClient, ThreadJobRunner, Transcriber
from backend.app.services.pipeline import ProcessingPipeline


@dataclass
class AppServices:
    settings: Settings
    store: SessionStore
    pipeline: ProcessingPipeline
    runner: JobRunner
    docx: DocxGenerator


def _default_transcriber() -> Transcriber:
    from backend.app.api.transcription import _get_transcriber

    return _get_transcriber()


def _default_llm() -> LLMClient:
    from backend.app.api.gigachat import _get_client

    return _get_client()


def create_services(
    settings: Settings | None = None,
    transcriber_factory: Callable[[], Transcriber] | None = None,
    llm_factory: Callable[[], LLMClient] | None = None,
    runner: JobRunner | None = None,
) -> AppServices:
    resolved = settings or Settings.from_env()
    store = SessionStore(resolved.sessions_dir)
    pipeline = ProcessingPipeline(
        store,
        resolved,
        transcriber_factory or _default_transcriber,
        llm_factory or _default_llm,
    )
    return AppServices(
        settings=resolved,
        store=store,
        pipeline=pipeline,
        runner=runner or ThreadJobRunner(),
        docx=DocxGenerator(resolved),
    )


_services: AppServices | None = None
_lock = threading.Lock()


def get_services() -> AppServices:
    global _services
    if _services is None:
        with _lock:
            if _services is None:
                load_dotenv()
                _services = create_services()
    return _services


def set_services(services: AppServices | None) -> None:
    global _services
    _services = services
