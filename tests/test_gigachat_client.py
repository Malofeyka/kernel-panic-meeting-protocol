import json

import httpx
import pytest

from backend.app.schemas.transcription import MeetingTranscription, TranscriptionSegment
from backend.app.services.gigachat_client import (
    GigaChatClient,
    GigaChatError,
    GigaChatUnavailableError,
)

_BASE_URL = "http://127.0.0.1:8080"


def _transcription() -> MeetingTranscription:
    return MeetingTranscription(
        model="e2e_rnnt",
        source="meeting.mp4",
        text="Обсудили открытие школы. Решили продолжить подготовку.",
        segments=[
            TranscriptionSegment(start=0.0, end=1.5, text="Обсудили открытие школы."),
            TranscriptionSegment(start=1.5, end=3.0, text="Решили продолжить подготовку."),
        ],
    )


def test_chat_sends_openai_compatible_request():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == f"{_BASE_URL}/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload == {
            "messages": [
                {"role": "system", "content": "Отвечай кратко"},
                {"role": "user", "content": "Суть текста"},
            ],
            "temperature": 0.0,
            "max_tokens": 128,
            "stream": False,
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "  Краткий ответ  "}}]},
        )

    client = GigaChatClient(base_url=_BASE_URL, transport=httpx.MockTransport(handler))
    try:
        result = client.chat(
            "Суть текста",
            system_prompt="Отвечай кратко",
            max_tokens=128,
        )
    finally:
        client.close()

    assert result == "Краткий ответ"


def test_summary_embeds_complete_transcription_json():
    transcription = _transcription()

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["messages"][0]["role"] == "system"
        assert transcription.model_dump_json() in payload["messages"][1]["content"]
        assert payload["temperature"] == 0.0
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Суть совещания"}}]},
        )

    client = GigaChatClient(base_url=_BASE_URL, transport=httpx.MockTransport(handler))
    try:
        result = client.summarize(transcription)
    finally:
        client.close()

    assert result == "Суть совещания"


def test_health_accepts_only_successful_response():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        return httpx.Response(200, json={"status": "ok"})

    client = GigaChatClient(base_url=_BASE_URL, transport=httpx.MockTransport(handler))
    try:
        client.health()
    finally:
        client.close()

    assert requests == ["/health"]


def test_connection_error_has_clear_exception():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = GigaChatClient(base_url=_BASE_URL, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(GigaChatUnavailableError, match="недоступен|Не удалось"):
            client.chat("Привет")
    finally:
        client.close()


def test_upstream_error_has_clear_exception():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "failed"})

    client = GigaChatClient(base_url=_BASE_URL, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(GigaChatError, match="HTTP 500"):
            client.chat("Привет")
    finally:
        client.close()


def test_external_url_is_rejected():
    with pytest.raises(ValueError, match="loopback"):
        GigaChatClient(base_url="https://example.com")
