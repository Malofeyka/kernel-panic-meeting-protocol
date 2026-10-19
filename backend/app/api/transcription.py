"""
Эндпоинты локальной транскрибации (STT) на базе GigaAM.

Интеграционная точка для Backend: загрузка аудио/видео -> JSON со стенограммой.
Модель загружается лениво один раз на процесс (синглтон), чтобы не перечитывать
веса на каждый запрос. Эндпоинт объявлен синхронным (def), поэтому FastAPI
выполняет его в threadpool и event loop не блокируется.
"""

import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError

from backend.app.schemas.transcription import DomainVocabulary, MeetingTranscription
from backend.app.services.gigaam_transcriber import GigaAMTranscriber

router = APIRouter(prefix="/api/transcription", tags=["Транскрибация (STT)"])

_transcriber: GigaAMTranscriber | None = None


def _get_transcriber() -> GigaAMTranscriber:
    """Ленивая инициализация единственного экземпляра транскрибера."""
    global _transcriber
    if _transcriber is None:
        load_dotenv()
        hf_token = os.getenv("HF_TOKEN") or os.getenv("hf")
        if hf_token:
            os.environ["HF_TOKEN"] = hf_token

        device = os.getenv("GIGAAM_DEVICE") or None
        _transcriber = GigaAMTranscriber(
            model_name=os.getenv("GIGAAM_MODEL", "e2e_rnnt"),
            device=device,
            batch_size=int(os.getenv("GIGAAM_BATCH_SIZE", "4")),
        )
    return _transcriber


def _parse_vocabulary(raw_vocabulary: str | None) -> DomainVocabulary | None:
    if raw_vocabulary is None or not raw_vocabulary.strip():
        return None
    try:
        return DomainVocabulary.model_validate_json(raw_vocabulary)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Доменный словарь должен быть JSON-объектом с поддерживаемыми полями",
        ) from exc


@router.post(
    "",
    response_model=MeetingTranscription,
    summary="Локальная транскрибация аудиозаписи совещания (GigaAM, офлайн)",
)
def transcribe_audio(
    audio_file: UploadFile = File(
        ..., description="Аудио- или видеофайл совещания (WAV, MP3, M4A, MP4...)"
    ),
    vocabulary: str | None = Form(
        default=None, description="Необязательный JSON-объект доменного словаря"
    ),
) -> MeetingTranscription:
    domain_vocabulary = _parse_vocabulary(vocabulary)
    suffix = Path(audio_file.filename or "audio.mp4").suffix or ".mp4"
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_file.file.read())
            tmp_path = Path(tmp.name)

        if domain_vocabulary is None:
            return _get_transcriber().transcribe(tmp_path)
        return _get_transcriber().transcribe(tmp_path, vocabulary=domain_vocabulary)
    except HTTPException:
        raise
    except Exception as exc:  # ошибки модели возвращаем бэкенду читаемым JSON
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка транскрибации: {exc}",
        ) from exc
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
