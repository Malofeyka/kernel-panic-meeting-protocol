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
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from backend.app.schemas.transcription import MeetingTranscription
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


@router.post(
    "",
    response_model=MeetingTranscription,
    summary="Локальная транскрибация аудиозаписи совещания (GigaAM, офлайн)",
)
def transcribe_audio(
    audio_file: UploadFile = File(
        ..., description="Аудио- или видеофайл совещания (WAV, MP3, M4A, MP4...)"
    ),
) -> MeetingTranscription:
    suffix = Path(audio_file.filename or "audio.mp4").suffix or ".mp4"
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_file.file.read())
            tmp_path = Path(tmp.name)

        return _get_transcriber().transcribe(tmp_path)
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
