"""Локальное файловое хранилище рабочих сессий (без внешних БД, всё внутри контура).

Структура:
    <DATA_DIR>/sessions/<session_id>/session.json   — состояние сессии и черновик
    <DATA_DIR>/sessions/<session_id>/files/...       — загруженные материалы
    <DATA_DIR>/sessions/<session_id>/transcript.json — результат STT (кэш)
    <DATA_DIR>/sessions/<session_id>/export/...      — сформированный .docx

Запись атомарная (временный файл + os.replace), доступ сериализован блокировкой.
"""

import os
import shutil
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from backend.app.schemas.api_contract import BUSY_STEPS, ProcessingStep
from backend.app.schemas.session import SessionRecord
from backend.app.schemas.transcription import MeetingTranscription

_COPY_CHUNK = 1024 * 1024


class SessionNotFoundError(KeyError):
    pass


class UploadTooLargeError(ValueError):
    pass


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)


class SessionStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _validate_id(session_id: str) -> str:
        try:
            return str(uuid.UUID(session_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise SessionNotFoundError(session_id) from exc

    def session_dir(self, session_id: str) -> Path:
        return self._root / self._validate_id(session_id)

    def files_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "files"

    def export_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "export"

    def _record_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "session.json"

    def _transcript_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "transcript.json"

    def create(self, record: SessionRecord) -> SessionRecord:
        with self._lock:
            self.files_dir(record.session_id).mkdir(parents=True, exist_ok=True)
            self._write(record)
        return record

    def _write(self, record: SessionRecord) -> None:
        record.updated_at = datetime.now(UTC)
        _atomic_write(self._record_path(record.session_id), record.model_dump_json(indent=2))

    def get(self, session_id: str) -> SessionRecord:
        with self._lock:
            path = self._record_path(session_id)
            if not path.is_file():
                raise SessionNotFoundError(session_id)
            return SessionRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, record: SessionRecord) -> SessionRecord:
        with self._lock:
            if not self._record_path(record.session_id).is_file():
                raise SessionNotFoundError(record.session_id)
            self._write(record)
        return record

    def update(self, session_id: str, mutator: Callable[[SessionRecord], None]) -> SessionRecord:
        with self._lock:
            record = self.get(session_id)
            mutator(record)
            self._write(record)
            return record

    def list(self) -> list[SessionRecord]:
        records: list[SessionRecord] = []
        with self._lock:
            for path in self._root.glob("*/session.json"):
                try:
                    records.append(SessionRecord.model_validate_json(path.read_text("utf-8")))
                except ValueError:
                    continue
        return sorted(records, key=lambda record: record.created_at, reverse=True)

    def delete(self, session_id: str) -> None:
        with self._lock:
            directory = self.session_dir(session_id)
            if not directory.is_dir():
                raise SessionNotFoundError(session_id)
            shutil.rmtree(directory)

    def save_upload(
        self, session_id: str, source: BinaryIO, stored_name: str, max_bytes: int
    ) -> int:
        target = self.files_dir(session_id) / stored_name
        target.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        try:
            with target.open("wb") as destination:
                while chunk := source.read(_COPY_CHUNK):
                    size += len(chunk)
                    if size > max_bytes:
                        raise UploadTooLargeError(stored_name)
                    destination.write(chunk)
        except UploadTooLargeError:
            target.unlink(missing_ok=True)
            raise
        return size

    def clear_files(self, session_id: str) -> None:
        with self._lock:
            for directory in (self.files_dir(session_id), self.export_dir(session_id)):
                if directory.is_dir():
                    shutil.rmtree(directory)
            self._transcript_path(session_id).unlink(missing_ok=True)
            self.files_dir(session_id).mkdir(parents=True, exist_ok=True)

    def save_transcript(self, session_id: str, transcription: MeetingTranscription) -> None:
        _atomic_write(self._transcript_path(session_id), transcription.model_dump_json(indent=2))

    def load_transcript(self, session_id: str) -> MeetingTranscription | None:
        path = self._transcript_path(session_id)
        if not path.is_file():
            return None
        return MeetingTranscription.model_validate_json(path.read_text(encoding="utf-8"))

    def recover_interrupted(self) -> int:
        """После перезапуска сервера незавершённые задачи помечаются как прерванные."""
        recovered = 0
        for record in self.list():
            if record.status not in BUSY_STEPS:
                continue

            def mark(item: SessionRecord) -> None:
                if item.status == ProcessingStep.REFINING:
                    item.refund_revision_cycle()
                if item.has_generated_draft:
                    item.status = ProcessingStep.READY
                    item.progress = 100
                    item.step_description = "Предыдущая операция прервана перезапуском сервера."
                else:
                    item.status = ProcessingStep.FAILED
                    item.error_message = (
                        "Обработка прервана перезапуском сервера. Нажмите «Повторить»."
                    )

            self.update(record.session_id, mark)
            recovered += 1
        return recovered
