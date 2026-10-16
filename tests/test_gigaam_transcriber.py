from types import SimpleNamespace
from unittest.mock import Mock

import pytest

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


def test_transcription_rejects_missing_file(tmp_path):
    transcriber = GigaAMTranscriber(model=Mock())

    with pytest.raises(FileNotFoundError):
        transcriber.transcribe(tmp_path / "missing.wav")


def test_transcription_rejects_invalid_batch_size():
    with pytest.raises(ValueError):
        GigaAMTranscriber(model=Mock(), batch_size=0)
