from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.app.schemas.transcription import DomainVocabulary
from backend.app.services.gigaam_transcriber import GigaAMTranscriber


def test_transcription_contains_llm_text_and_timestamps(tmp_path):
    audio_path = tmp_path / "meeting.mp4"
    audio_path.write_bytes(b"test")
    model = Mock()
    model.transcribe_longform.return_value = [
        SimpleNamespace(start=0.0, end=1.25, text="Первый фрагмент."),
        SimpleNamespace(start=1.25, end=2.5, text="Второй фрагмент."),
    ]
    transcriber = GigaAMTranscriber(model=model, batch_size=2)

    result = transcriber.transcribe(audio_path)

    assert result.text == "Первый фрагмент. Второй фрагмент."
    assert result.source == "meeting.mp4"
    assert result.model_dump()["segments"] == [
        {"start": 0.0, "end": 1.25, "text": "Первый фрагмент."},
        {"start": 1.25, "end": 2.5, "text": "Второй фрагмент."},
    ]
    model.transcribe_longform.assert_called_once_with(str(audio_path), fr_batch_size=2)


def test_transcription_with_empty_vocabulary_preserves_result(tmp_path):
    audio_path = tmp_path / "meeting.wav"
    audio_path.write_bytes(b"test")
    model = Mock()
    model.transcribe_longform.return_value = [
        SimpleNamespace(start=0.0, end=1.25, text="Егэ остаётся как распознано."),
    ]
    transcriber = GigaAMTranscriber(model=model, batch_size=2)

    result = transcriber.transcribe(audio_path, vocabulary=DomainVocabulary())

    assert result.text == "Егэ остаётся как распознано."
    assert result.model_dump()["segments"] == [
        {"start": 0.0, "end": 1.25, "text": "Егэ остаётся как распознано."}
    ]
    model.transcribe_longform.assert_called_once_with(str(audio_path), fr_batch_size=2)


def test_transcription_with_vocabulary_uses_fallback_and_preserves_timestamps(tmp_path):
    audio_path = tmp_path / "meeting.wav"
    audio_path.write_bytes(b"test")
    raw_segments = [
        SimpleNamespace(start=0.0, end=1.25, text="Егэ."),
        SimpleNamespace(start=1.25, end=2.5, text="Второй фрагмент."),
    ]
    model = Mock()
    model.transcribe_longform.return_value = raw_segments
    transcriber = GigaAMTranscriber(model=model, batch_size=2)

    result = transcriber.transcribe(audio_path, vocabulary=DomainVocabulary(abbreviations=["ЕГЭ"]))

    assert result.text == "ЕГЭ. Второй фрагмент."
    assert result.model_dump()["segments"] == [
        {"start": 0.0, "end": 1.25, "text": "ЕГЭ."},
        {"start": 1.25, "end": 2.5, "text": "Второй фрагмент."},
    ]
    assert raw_segments[0].text == "Егэ."
    model.transcribe_longform.assert_called_once_with(str(audio_path), fr_batch_size=2)


def test_transcription_rejects_missing_file(tmp_path):
    transcriber = GigaAMTranscriber(model=Mock())

    with pytest.raises(FileNotFoundError):
        transcriber.transcribe(tmp_path / "missing.wav")


def test_transcription_rejects_invalid_batch_size():
    with pytest.raises(ValueError):
        GigaAMTranscriber(model=Mock(), batch_size=0)


def test_resolve_vad_param_precedence(monkeypatch):
    from backend.app.services.gigaam_transcriber import _resolve_vad_param

    # 1. Явный аргумент имеет наивысший приоритет
    assert _resolve_vad_param("VAD_TEST", 1.5, 0.0) == 1.5

    # 2. Переменная окружения
    monkeypatch.setenv("VAD_TEST", "2.5")
    assert _resolve_vad_param("VAD_TEST", None, 0.0) == 2.5

    # 3. Дефолтное значение
    monkeypatch.delenv("VAD_TEST", raising=False)
    assert _resolve_vad_param("VAD_TEST", None, 3.5) == 3.5


def test_gigaam_transcriber_custom_vad_params():
    transcriber = GigaAMTranscriber(
        model=Mock(),
        batch_size=2,
        min_duration_on=0.5,
        min_duration_off=0.8,
    )
    assert transcriber._min_duration_on == 0.5
    assert transcriber._min_duration_off == 0.8
