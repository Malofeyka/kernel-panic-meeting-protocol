import io
from pathlib import Path

import pytest

from backend.app.core.config import Settings
from backend.app.persistence.session_store import (
    SessionNotFoundError,
    SessionStore,
    UploadTooLargeError,
)
from backend.app.schemas.api_contract import ProcessingStep
from backend.app.schemas.protocol import ProtocolDraft, ProtocolMetadata, RevisionCycleState
from backend.app.schemas.session import SessionRecord
from backend.app.services.interfaces import ThreadJobRunner
from tests.conftest import make_transcription

SESSION_ID = "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"


def _record(session_id: str = SESSION_ID) -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        draft=ProtocolDraft(
            session_id=session_id, metadata=ProtocolMetadata(meeting_date="20.10.2026")
        ),
    )


def test_store_roundtrip_and_files(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    store.create(_record())
    assert store.get(SESSION_ID).status == ProcessingStep.IDLE

    size = store.save_upload(SESSION_ID, io.BytesIO(b"12345"), "audio.mp3", max_bytes=10)
    assert size == 5 and (store.files_dir(SESSION_ID) / "audio.mp3").is_file()
    with pytest.raises(UploadTooLargeError):
        store.save_upload(SESSION_ID, io.BytesIO(b"x" * 11), "big.mp3", max_bytes=10)
    assert not (store.files_dir(SESSION_ID) / "big.mp3").exists()

    store.save_transcript(SESSION_ID, make_transcription())
    loaded = store.load_transcript(SESSION_ID)
    assert loaded is not None and len(loaded.segments) == 10
    store.clear_files(SESSION_ID)
    assert store.load_transcript(SESSION_ID) is None
    assert not (store.files_dir(SESSION_ID) / "audio.mp3").exists()

    assert [r.session_id for r in store.list()] == [SESSION_ID]
    store.delete(SESSION_ID)
    with pytest.raises(SessionNotFoundError):
        store.get(SESSION_ID)
    with pytest.raises(SessionNotFoundError):
        store.delete(SESSION_ID)
    with pytest.raises(SessionNotFoundError):
        store.save(_record())
    with pytest.raises(SessionNotFoundError):
        store.get("../../etc/passwd")  # защита от обхода путей


def test_recover_interrupted(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    ids = [
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
        "33333333-3333-3333-3333-333333333333",
    ]
    for session_id in ids:
        store.create(_record(session_id))

    def transcribing(record: SessionRecord) -> None:
        record.status = ProcessingStep.TRANSCRIBING

    def refining(record: SessionRecord) -> None:
        record.status = ProcessingStep.REFINING
        record.has_generated_draft = True
        record.draft.revision_cycle = RevisionCycleState(
            current_cycle=2, is_escalated_to_manual=True
        )

    store.update(ids[0], transcribing)
    store.update(ids[1], refining)
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "session.json").write_text("{", encoding="utf-8")

    assert store.recover_interrupted() == 2
    assert store.get(ids[0]).status == ProcessingStep.FAILED
    refined = store.get(ids[1])
    assert refined.status == ProcessingStep.READY
    assert refined.draft.revision_cycle.current_cycle == 1
    assert refined.draft.revision_cycle.is_escalated_to_manual is False
    assert store.get(ids[2]).status == ProcessingStep.IDLE


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", "custom")
    monkeypatch.setenv("MAX_UPLOAD_MB", "5")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.2")
    monkeypatch.setenv("DROP_UNGROUNDED_ITEMS", "нет")
    settings = Settings.from_env()
    assert settings.sessions_dir == Path("custom") / "sessions"
    assert settings.max_upload_bytes == 5 * 1024 * 1024
    assert settings.llm_temperature == 0.2
    assert settings.drop_ungrounded_items is False


def test_thread_runner_executes_jobs() -> None:
    import threading

    done = threading.Event()
    runner = ThreadJobRunner()
    runner.submit(done.set)
    assert done.wait(timeout=5)
    runner.shutdown()
