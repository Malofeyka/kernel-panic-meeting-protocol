"""
Сквозные тесты API-контракта: полный сценарий приёмки
«загрузка -> проект протокола -> правки (<= 2 кругов ИИ) -> Word».
"""

import io
import json
from typing import Any

import pytest
from docx import Document
from fastapi.testclient import TestClient

from backend.app.api.dependencies import AppServices, create_services, set_services
from backend.app.core.config import Settings
from backend.app.main import app
from backend.app.schemas.api_contract import ProcessingStep
from backend.app.services.interfaces import InlineJobRunner
from tests.conftest import (
    AGENDA_TXT,
    ARCHIVE_TXT,
    ATTENDEES_TXT,
    MEETING_DATE,
    FakeLLM,
    FakeTranscriber,
)

client = TestClient(app)


def _create(**payload: Any) -> str:
    body = {"meeting_title": "Аппаратное совещание", "meeting_date": MEETING_DATE, **payload}
    response = client.post("/api/sessions/create", json=body)
    assert response.status_code == 201
    return str(response.json()["session_id"])


def _upload_full_set(session_id: str) -> Any:
    files: list[tuple[str, tuple[str, bytes, str]]] = [
        ("audio_file", ("meeting.mp3", b"fake audio", "audio/mpeg")),
        ("agenda_file", ("agenda.txt", AGENDA_TXT.encode("utf-8"), "text/plain")),
        ("attendees_file", ("attendees.txt", ATTENDEES_TXT.encode("cp1251"), "text/plain")),
        ("archive_files", ("protocol_11.txt", ARCHIVE_TXT.encode("utf-8"), "text/plain")),
    ]
    return client.post(f"/api/sessions/{session_id}/upload", files=files)


def _action_by_task(draft: dict[str, Any], fragment: str) -> dict[str, Any]:
    for item in draft["agenda_items"]:
        for action in item["action_items"]:
            if fragment in action["task"]:
                return dict(action)
    raise AssertionError(f"Поручение «{fragment}» не найдено")


def test_health_check() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["isolated_mode"] is True
    assert data["max_revision_cycles"] == 2


def test_create_session_defaults_and_validation() -> None:
    response = client.post("/api/sessions/create")
    assert response.status_code == 201
    assert response.json()["status"] == ProcessingStep.IDLE

    bad = client.post("/api/sessions/create", json={"meeting_date": "2026-10-20"})
    assert bad.status_code == 422

    session_id = _create(protocol_number="12")
    draft = client.get(f"/api/sessions/{session_id}/draft").json()
    assert draft["metadata"]["meeting_date"] == MEETING_DATE
    assert draft["metadata"]["protocol_number"] == "12"
    assert draft["metadata"]["chairperson"] is None  # не выдумываем председателя
    assert draft["revision_cycle"] == {
        "current_cycle": 0,
        "max_cycles": 2,
        "is_escalated_to_manual": False,
    }


def test_full_acceptance_scenario(fake_transcriber: FakeTranscriber) -> None:
    session_id = _create(protocol_number="12")

    upload = _upload_full_set(session_id)
    assert upload.status_code == 200, upload.text
    status_body = client.get(f"/api/sessions/{session_id}/status").json()
    assert status_body["status"] == ProcessingStep.READY
    assert status_body["progress_percent"] == 100
    assert status_body["error_message"] is None

    # словарь для STT собран из списка участников
    _, vocabulary = fake_transcriber.calls[0]
    assert vocabulary is not None
    assert "Петров Петр Петрович" in vocabulary.people

    details = client.get(f"/api/sessions/{session_id}").json()
    assert details["has_draft"] is True
    assert details["has_transcript"] is True
    assert details["files"]["audio"] == "meeting.mp3"
    assert details["files"]["archive"] == ["protocol_11.txt"]

    draft = client.get(f"/api/sessions/{session_id}/draft").json()
    meta = draft["metadata"]
    assert meta["chairperson"] == "Иванов И.И."
    assert meta["secretary"] == "Кузнецова А.В."
    assert [a["short_name"] for a in meta["attendees"]] == [
        "Иванов И.И.",
        "Петров П.П.",
        "Сидорова С.С.",
        "Кузнецова А.В.",
    ]

    items = draft["agenda_items"]
    assert [item["topic"] for item in items] == [
        "О готовности к государственной итоговой аттестации",
        "Об итогах региональной олимпиады",
    ]
    assert items[0]["reporter"] == "Петров П.П."
    assert [d["text"] for d in items[0]["decisions"]] == ["Принять информацию к сведению"]
    assert items[1]["decisions"] == []  # выдуманное решение отклонено

    ppe = _action_by_task(draft, "пунктов проведения экзаменов")
    assert ppe["assignee"] == "Петров П.П."
    assert ppe["assignee_role"] == "начальник отдела контроля качества образования"
    assert ppe["due_date"] == "15.11.2026"
    assert ppe["status"] == "valid"
    assert ppe["source_start"] == 40.0

    instructions = _action_by_task(draft, "инструкции")
    assert instructions["assignee"] is None
    assert instructions["due_date"] is None  # «до 30 ноября» не звучало
    assert instructions["status"] == "missing_assignee_and_date"

    report = _action_by_task(draft, "отчет")
    assert report["assignee"] == "Сидорова С.С."
    assert report["due_date"] == "30.10.2026"

    letter = _action_by_task(draft, "письмо")
    assert letter["assignee"] == "Иванов И.И."
    assert letter["due_date"] is None

    all_tasks = [a["task"] for item in items for a in item["action_items"]]
    assert not any("Рособрнадзор" in task for task in all_tasks)  # галлюцинация отсечена

    analytics = draft["analytics"]
    gap_types = {gap["type"] for gap in analytics["gaps"]}
    assert {
        "MISSING_DUE_DATE",
        "MISSING_ASSIGNEE",
        "VAGUE_DUE_DATE",
        "REJECTED_UNGROUNDED",
    } <= gap_types
    assert all(
        gap["action_item_id"] for gap in analytics["gaps"] if gap["type"] == "MISSING_ASSIGNEE"
    )
    repeated = [r for r in analytics["risks"] if r["type"] == "REPEATED_ASSIGNMENT"]
    assert repeated and repeated[0]["action_item_ids"] == [report["id"]]
    assert "№ 11" in repeated[0]["archive_reference"]

    transcript = client.get(f"/api/sessions/{session_id}/transcript").json()
    assert len(transcript["segments"]) == 10

    # ручная правка не расходует лимит, статус пересчитывается
    for item in draft["agenda_items"]:
        for action in item["action_items"]:
            if action["id"] == instructions["id"]:
                action["due_date"] = "01.12.2026"
    manual = client.post(
        f"/api/sessions/{session_id}/refine",
        json={"action": "manual_save", "updated_agenda_items": draft["agenda_items"]},
    )
    assert manual.status_code == 200
    manual_body = manual.json()
    assert manual_body["revision_cycle"]["current_cycle"] == 0
    assert _action_by_task(manual_body["updated_draft"], "инструкции")["status"] == (
        "missing_assignee"
    )

    # круг 1: ИИ-правка
    refine_1 = client.post(
        f"/api/sessions/{session_id}/refine",
        json={
            "action": "ai_regenerate",
            "user_feedback": "По инструкциям для наблюдателей ответственная Сидорова, "
            "срок до 25 ноября",
        },
    )
    assert refine_1.status_code == 200, refine_1.text
    body_1 = refine_1.json()
    assert body_1["status"] == ProcessingStep.READY
    assert body_1["revision_cycle"]["current_cycle"] == 1
    assert body_1["revision_cycle"]["is_escalated_to_manual"] is False
    updated = _action_by_task(body_1["updated_draft"], "инструкции")
    assert updated["assignee"] == "Сидорова С.С."
    assert updated["due_date"] == "25.11.2026"
    assert "Не применено" in body_1["message"]  # оборудование не подтверждено
    assert not any(
        "оборудование" in a["task"]
        for item in body_1["updated_draft"]["agenda_items"]
        for a in item["action_items"]
    )

    # круг 2: достижение лимита
    refine_2 = client.post(
        f"/api/sessions/{session_id}/refine",
        json={"action": "ai_regenerate", "user_feedback": "Уточнить ответственного по пункту 1"},
    )
    assert refine_2.status_code == 200
    assert refine_2.json()["revision_cycle"]["current_cycle"] == 2
    assert refine_2.json()["revision_cycle"]["is_escalated_to_manual"] is True

    # круг 3: блокировка
    refine_3 = client.post(
        f"/api/sessions/{session_id}/refine",
        json={"action": "ai_regenerate", "user_feedback": "Еще один круг генерации"},
    )
    assert refine_3.status_code == 400
    assert "Превышен лимит автоматических кругов правок" in refine_3.json()["detail"]

    # ручная доработка после эскалации доступна
    manual_after = client.post(f"/api/sessions/{session_id}/refine", json={"action": "manual_save"})
    assert manual_after.status_code == 200

    # экспорт и скачивание
    export = client.post(f"/api/sessions/{session_id}/export")
    assert export.status_code == 200
    export_body = export.json()
    assert export_body["file_name"].endswith(".docx")
    assert export_body["warnings"] == []
    download = client.get(export_body["download_url"])
    assert download.status_code == 200
    assert download.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )
    document = Document(io.BytesIO(download.content))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "ПРОТОКОЛ" in text
    assert "Принять информацию к сведению." in text
    assert "до 15.11.2026" in text
    table_text = "\n".join(c.text for row in document.tables[0].rows for c in row.cells)
    assert "Петров П.П." in table_text

    details = client.get(f"/api/sessions/{session_id}").json()
    assert details["export"]["download_url"] == export_body["download_url"]

    listed = client.get("/api/sessions").json()
    assert any(item["session_id"] == session_id for item in listed)

    assert client.delete(f"/api/sessions/{session_id}").status_code == 204
    assert client.get(f"/api/sessions/{session_id}/status").status_code == 404


def test_upload_transcript_instead_of_audio(fake_transcriber: FakeTranscriber) -> None:
    session_id = _create()
    payload = {
        "model": "e2e_rnnt",
        "source": "meeting.mp3",
        "text": "x",
        "segments": [
            {"start": i * 10.0, "end": i * 10.0 + 9, "text": t}
            for i, t in enumerate(fake_transcriber.transcription.model_dump()["text"].split(". "))
        ],
    }
    response = client.post(
        f"/api/sessions/{session_id}/upload",
        files={
            "transcript_file": ("transcript.json", json.dumps(payload).encode(), "application/json")
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == ProcessingStep.READY
    assert fake_transcriber.calls == []  # STT не запускался
    draft = client.get(f"/api/sessions/{session_id}/draft").json()
    # без повестки поручения группируются по темам, без списка участников — флаг в аналитике
    assert draft["agenda_items"]
    descriptions = [gap["description"] for gap in draft["analytics"]["gaps"]]
    assert any("Список участников не загружен" in text for text in descriptions)


def test_upload_validation_errors() -> None:
    session_id = _create()
    missing = client.post(
        f"/api/sessions/{session_id}/upload",
        files={"agenda_file": ("agenda.txt", b"1. Tema", "text/plain")},
    )
    assert missing.status_code == 400

    bad_audio = client.post(
        f"/api/sessions/{session_id}/upload",
        files={"audio_file": ("meeting.exe", b"x", "application/octet-stream")},
    )
    assert bad_audio.status_code == 400
    assert "не поддерживается" in bad_audio.json()["detail"]

    bad_template = client.post(
        f"/api/sessions/{session_id}/upload",
        files={
            "audio_file": ("meeting.mp3", b"x", "audio/mpeg"),
            "template_file": ("template.pdf", b"x", "application/pdf"),
        },
    )
    assert bad_template.status_code == 400

    assert (
        client.post(
            "/api/sessions/00000000-0000-0000-0000-000000000000/upload",
            files={"audio_file": ("a.mp3", b"x", "audio/mpeg")},
        ).status_code
        == 404
    )


def test_upload_too_large(
    tmp_path: Any, fake_llm: FakeLLM, fake_transcriber: FakeTranscriber
) -> None:
    small = create_services(
        settings=Settings(data_dir=tmp_path / "small", max_upload_mb=0),
        transcriber_factory=lambda: fake_transcriber,
        llm_factory=lambda: fake_llm,
        runner=InlineJobRunner(),
    )
    set_services(small)
    session_id = _create()
    response = client.post(
        f"/api/sessions/{session_id}/upload",
        files={"audio_file": ("meeting.mp3", b"too large", "audio/mpeg")},
    )
    assert response.status_code == 413
    status_body = client.get(f"/api/sessions/{session_id}/status").json()
    assert status_body["status"] == ProcessingStep.IDLE


def test_llm_unavailable_then_retry(fake_llm: FakeLLM, fake_transcriber: FakeTranscriber) -> None:
    session_id = _create()
    fake_llm.available = False
    assert _upload_full_set(session_id).status_code == 200
    failed = client.get(f"/api/sessions/{session_id}/status").json()
    assert failed["status"] == ProcessingStep.FAILED
    assert "GigaChat недоступна" in failed["error_message"]
    assert client.get(f"/api/sessions/{session_id}").json()["has_transcript"] is True

    fake_llm.available = True
    retry = client.post(f"/api/sessions/{session_id}/process")
    assert retry.status_code == 200
    assert retry.json()["status"] == ProcessingStep.READY
    assert len(fake_transcriber.calls) == 1  # STT не повторялся: стенограмма из кэша


def test_ai_refine_failure_refunds_cycle(fake_llm: FakeLLM) -> None:
    session_id = _create()
    _upload_full_set(session_id)
    fake_llm.available = False
    response = client.post(
        f"/api/sessions/{session_id}/refine",
        json={"action": "ai_regenerate", "user_feedback": "Уточни сроки"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == ProcessingStep.READY
    assert body["revision_cycle"]["current_cycle"] == 0
    assert "не выполнена" in body["message"]


def test_refine_guards(services: AppServices) -> None:
    session_id = _create()
    not_ready = client.post(
        f"/api/sessions/{session_id}/refine",
        json={"action": "ai_regenerate", "user_feedback": "Правка"},
    )
    assert not_ready.status_code == 409

    _upload_full_set(session_id)
    empty_feedback = client.post(
        f"/api/sessions/{session_id}/refine", json={"action": "ai_regenerate"}
    )
    assert empty_feedback.status_code == 400

    record = services.store.get(session_id)
    record.status = ProcessingStep.EXTRACTING
    services.store.save(record)
    busy = client.post(f"/api/sessions/{session_id}/refine", json={"action": "manual_save"})
    assert busy.status_code == 409
    assert client.post(f"/api/sessions/{session_id}/export").status_code == 409
    assert client.delete(f"/api/sessions/{session_id}").status_code == 409


def test_not_found_and_missing_artifacts() -> None:
    assert client.get("/api/sessions/non-existent-id/status").status_code == 404
    assert client.get("/api/sessions/non-existent-id").status_code == 404
    session_id = _create()
    assert client.get(f"/api/sessions/{session_id}/transcript").status_code == 404
    assert client.get(f"/api/sessions/{session_id}/download").status_code == 404
    assert client.post(f"/api/sessions/{session_id}/process").status_code == 400


@pytest.mark.parametrize("template_kind", ["plain", "tagged"])
def test_export_with_custom_template(template_kind: str) -> None:
    template = Document()
    if template_kind == "tagged":
        template.add_paragraph(
            "БЛАНК МИНИСТЕРСТВА. Протокол {{ meeting_date }} № {{ protocol_number }}"
        )
    else:
        template.add_paragraph("Бланк без полей")
    buffer = io.BytesIO()
    template.save(buffer)

    session_id = _create(protocol_number="7")
    client.post(
        f"/api/sessions/{session_id}/upload",
        files={
            "audio_file": ("meeting.mp3", b"x", "audio/mpeg"),
            "template_file": ("blank.docx", buffer.getvalue(), "application/octet-stream"),
        },
    )
    export = client.post(f"/api/sessions/{session_id}/export").json()
    content = client.get(export["download_url"]).content
    text = "\n".join(p.text for p in Document(io.BytesIO(content)).paragraphs)
    if template_kind == "tagged":
        assert export["warnings"] == []
        assert f"Протокол {MEETING_DATE} № 7" in text
    else:
        assert export["warnings"] and "не содержит полей" in export["warnings"][0]
        assert "ПРОТОКОЛ" in text
