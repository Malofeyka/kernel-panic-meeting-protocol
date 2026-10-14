"""
Тесты API-контракта и ключевой бизнес-логики сервиса протоколирования.
"""
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.schemas.protocol import (
    ProtocolDraft,
    ProtocolMetadata,
    AgendaItem,
    ActionItem,
    AnalyticsReport,
    RevisionCycleState
)
from backend.app.schemas.api_contract import ProcessingStep

client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["isolated_mode"] is True
    assert data["max_revision_cycles"] == 2


def test_create_session():
    response = client.post("/api/sessions/create", json={
        "meeting_title": "Оперативное совещание Министерства образования",
        "meeting_date": "20.10.2026"
    })
    assert response.status_code == 201
    data = response.json()
    assert "session_id" in data
    assert data["status"] == ProcessingStep.IDLE


def test_session_lifecycle_and_refine_limit():
    # 1. Создаем сессию
    create_res = client.post("/api/sessions/create", json={
        "meeting_title": "Аппаратное совещание",
        "meeting_date": "15.10.2026"
    })
    assert create_res.status_code == 201
    session_id = create_res.json()["session_id"]

    # 2. Проверяем статус сессии
    status_res = client.get(f"/api/sessions/{session_id}/status")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == ProcessingStep.IDLE

    # 3. Получаем черновик протокола
    draft_res = client.get(f"/api/sessions/{session_id}/draft")
    assert draft_res.status_code == 200
    draft_data = draft_res.json()
    assert draft_data["session_id"] == session_id
    assert draft_data["revision_cycle"]["current_cycle"] == 0
    assert draft_data["revision_cycle"]["max_cycles"] == 2

    # 4. Круг правок 1 (ИИ-генерация)
    refine_1 = client.post(f"/api/sessions/{session_id}/refine", json={
        "action": "ai_regenerate",
        "user_feedback": "Добавить пункт повестки об итогах олимпиад"
    })
    assert refine_1.status_code == 200
    assert refine_1.json()["revision_cycle"]["current_cycle"] == 1
    assert refine_1.json()["revision_cycle"]["is_escalated_to_manual"] is False

    # 5. Ручное сохранение (не должно увеличивать счетчик кругов)
    manual_save = client.post(f"/api/sessions/{session_id}/refine", json={
        "action": "manual_save",
        "user_feedback": "Точечная правка формулировки"
    })
    assert manual_save.status_code == 200
    assert manual_save.json()["revision_cycle"]["current_cycle"] == 1

    # 6. Круг правок 2 (ИИ-генерация - достижение лимита)
    refine_2 = client.post(f"/api/sessions/{session_id}/refine", json={
        "action": "ai_regenerate",
        "user_feedback": "Уточнить ответственного по пункту 1"
    })
    assert refine_2.status_code == 200
    assert refine_2.json()["revision_cycle"]["current_cycle"] == 2
    assert refine_2.json()["revision_cycle"]["is_escalated_to_manual"] is True

    # 7. Круг правок 3 (Попытка превысить лимит -> 400 Bad Request)
    refine_3 = client.post(f"/api/sessions/{session_id}/refine", json={
        "action": "ai_regenerate",
        "user_feedback": "Еще один круг генерации"
    })
    assert refine_3.status_code == 400
    assert "Превышен лимит автоматических кругов правок" in refine_3.json()["detail"]

    # 8. Экспорт DOCX
    export_res = client.post(f"/api/sessions/{session_id}/export")
    assert export_res.status_code == 200
    assert "download_url" in export_res.json()
    assert export_res.json()["file_name"].endswith(".docx")


def test_session_not_found():
    res = client.get("/api/sessions/non-existent-id/status")
    assert res.status_code == 404
