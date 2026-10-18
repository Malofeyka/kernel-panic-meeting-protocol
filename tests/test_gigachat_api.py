from unittest.mock import Mock

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas.transcription import MeetingTranscription
from backend.app.services.gigachat_client import GigaChatUnavailableError

client = TestClient(app)


def test_gigachat_chat_endpoint(monkeypatch):
    service = Mock()
    service.chat.return_value = "Краткий ответ"
    monkeypatch.setattr("backend.app.api.gigachat._get_client", lambda: service)

    response = client.post(
        "/api/gigachat/chat",
        json={
            "prompt": "Передай суть",
            "system_prompt": "Отвечай кратко",
            "temperature": 0.0,
            "max_tokens": 256,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"text": "Краткий ответ"}
    service.chat.assert_called_once_with(
        prompt="Передай суть",
        system_prompt="Отвечай кратко",
        temperature=0.0,
        max_tokens=256,
    )


def test_gigachat_summary_endpoint_accepts_transcription_json(monkeypatch):
    service = Mock()
    service.summarize.return_value = "Суть совещания"
    monkeypatch.setattr("backend.app.api.gigachat._get_client", lambda: service)
    transcription = {
        "model": "e2e_rnnt",
        "source": "meeting.mp4",
        "text": "Обсудили открытие школы.",
        "segments": [{"start": 0.0, "end": 1.5, "text": "Обсудили открытие школы."}],
    }

    response = client.post("/api/gigachat/summary", json=transcription)

    assert response.status_code == 200
    assert response.json() == {"summary": "Суть совещания"}
    argument = service.summarize.call_args.args[0]
    assert isinstance(argument, MeetingTranscription)
    assert argument.model_dump() == transcription


def test_gigachat_health_endpoint(monkeypatch):
    service = Mock()
    monkeypatch.setattr("backend.app.api.gigachat._get_client", lambda: service)

    response = client.get("/api/gigachat/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    service.health.assert_called_once_with()


def test_gigachat_endpoint_returns_503_when_model_is_unavailable(monkeypatch):
    service = Mock()
    service.health.side_effect = GigaChatUnavailableError("Сервер не запущен")
    monkeypatch.setattr("backend.app.api.gigachat._get_client", lambda: service)

    response = client.get("/api/gigachat/health")

    assert response.status_code == 503
    assert response.json() == {"detail": "Сервер не запущен"}
