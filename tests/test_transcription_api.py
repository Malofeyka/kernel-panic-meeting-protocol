from unittest.mock import Mock

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas.transcription import MeetingTranscription, TranscriptionSegment

client = TestClient(app)


def test_transcribe_audio_endpoint_success(monkeypatch):
    mock_service = Mock()
    mock_result = MeetingTranscription(
        model="e2e_rnnt",
        source="meeting.mp3",
        text="Приветствие и повестка совещания.",
        segments=[
            TranscriptionSegment(start=0.0, end=2.0, text="Приветствие и повестка совещания.")
        ],
    )
    mock_service.transcribe.return_value = mock_result
    monkeypatch.setattr("backend.app.api.transcription._get_transcriber", lambda: mock_service)

    response = client.post(
        "/api/transcription",
        files={"audio_file": ("meeting.mp3", b"dummy audio content", "audio/mpeg")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["model"] == "e2e_rnnt"
    assert data["text"] == "Приветствие и повестка совещания."
    assert len(data["segments"]) == 1
    mock_service.transcribe.assert_called_once()
    assert mock_service.transcribe.call_args.kwargs == {}


def test_transcribe_audio_endpoint_accepts_domain_vocabulary(monkeypatch):
    mock_service = Mock()
    mock_service.transcribe.return_value = MeetingTranscription(
        model="e2e_rnnt",
        source="meeting.mp3",
        text="ЕГЭ и ФОП.",
        segments=[],
    )
    monkeypatch.setattr("backend.app.api.transcription._get_transcriber", lambda: mock_service)

    response = client.post(
        "/api/transcription",
        files={"audio_file": ("meeting.mp3", b"dummy audio content", "audio/mpeg")},
        data={"vocabulary": '{"abbreviations": ["ЕГЭ", "егэ"], "terms": ["ФОП"]}'},
    )

    assert response.status_code == 200
    vocabulary = mock_service.transcribe.call_args.kwargs["vocabulary"]
    assert vocabulary.abbreviations == ["ЕГЭ"]
    assert vocabulary.terms == ["ФОП"]


def test_transcribe_audio_endpoint_rejects_invalid_vocabulary(monkeypatch):
    mock_get_transcriber = Mock()
    monkeypatch.setattr("backend.app.api.transcription._get_transcriber", mock_get_transcriber)

    response = client.post(
        "/api/transcription",
        files={"audio_file": ("meeting.mp3", b"dummy audio content", "audio/mpeg")},
        data={"vocabulary": '{"people": ["Иванов Иван"]'},
    )

    assert response.status_code == 422
    assert "Иванов" not in response.json()["detail"]
    mock_get_transcriber.assert_not_called()


def test_transcribe_audio_endpoint_handles_error(monkeypatch):
    mock_service = Mock()
    mock_service.transcribe.side_effect = RuntimeError("Ошибка декодирования аудио")
    monkeypatch.setattr("backend.app.api.transcription._get_transcriber", lambda: mock_service)

    response = client.post(
        "/api/transcription",
        files={"audio_file": ("corrupt.mp3", b"corrupted bytes", "audio/mpeg")},
    )

    assert response.status_code == 500
    assert "Ошибка транскрибации" in response.json()["detail"]
