import importlib
import os
from pathlib import Path
from typing import Any

from backend.app.schemas.transcription import MeetingTranscription, TranscriptionSegment

_DLL_DIRECTORY_HANDLE: Any | None = None

# Значения по умолчанию совпадают с hardcode в gigaam/vad_utils.py и переопределяются
# через аргументы конструктора или переменные окружения GIGAAM_MIN_DURATION_ON/OFF.
_DEFAULT_MIN_DURATION_ON = 0.0
_DEFAULT_MIN_DURATION_OFF = 0.0


def _resolve_vad_param(env_name: str, value: float | None, default: float) -> float:
    """Приоритет: аргумент конструктора > переменная окружения > значение по умолчанию."""
    if value is not None:
        return value
    raw = os.getenv(env_name)
    return float(raw) if raw not in (None, "") else default


class GigaAMTranscriber:
    def __init__(
        self,
        model_name: str = "e2e_rnnt",
        device: str | None = None,
        batch_size: int = 4,
        model: Any | None = None,
        min_duration_on: float | None = None,
        min_duration_off: float | None = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size должен быть не меньше 1")

        self._model_name = model_name
        self._batch_size = batch_size
        self._min_duration_on = _resolve_vad_param(
            "GIGAAM_MIN_DURATION_ON", min_duration_on, _DEFAULT_MIN_DURATION_ON
        )
        self._min_duration_off = _resolve_vad_param(
            "GIGAAM_MIN_DURATION_OFF", min_duration_off, _DEFAULT_MIN_DURATION_OFF
        )
        if model is not None:
            self._model = model
            return

        self._configure_ffmpeg()
        importlib.import_module("torchcodec")
        import gigaam
        import torch

        self._model = gigaam.load_model(model_name, device=device)
        self._apply_vad_params(
            resolved_device=torch.device(
                device if device else ("cuda" if torch.cuda.is_available() else "cpu")
            )
        )

    def _apply_vad_params(self, resolved_device: Any) -> None:
        """Переопределяет min_duration_on/off в pyannote-VAD пайплайне gigaam.

        Значения задаются хардкодом (0.0/0.0) внутри gigaam.vad_utils.get_pipeline,
        поэтому после создания пайплайна применяем свои параметры через instantiate.
        """
        from gigaam import vad_utils

        pipeline = vad_utils.get_pipeline(resolved_device)
        pipeline.instantiate(
            {
                "min_duration_on": self._min_duration_on,
                "min_duration_off": self._min_duration_off,
            }
        )

    @staticmethod
    def _configure_ffmpeg() -> None:
        if os.name != "nt":
            return

        global _DLL_DIRECTORY_HANDLE
        if _DLL_DIRECTORY_HANDLE is not None:
            return

        ffmpeg_bin = Path(os.getenv("FFMPEG_BIN", r"C:\ffmpeg8\bin")).resolve()
        if not (ffmpeg_bin / "ffmpeg.exe").is_file():
            raise RuntimeError(
                f"FFmpeg не найден в '{ffmpeg_bin}'. Укажите каталог bin в FFMPEG_BIN."
            )

        _DLL_DIRECTORY_HANDLE = os.add_dll_directory(str(ffmpeg_bin))
        os.environ["PATH"] = f"{ffmpeg_bin}{os.pathsep}{os.environ.get('PATH', '')}"

    def transcribe(self, audio_path: str | Path) -> MeetingTranscription:
        source_path = Path(audio_path)
        if not source_path.is_file():
            raise FileNotFoundError(f"Аудиофайл не найден: {source_path}")

        segments = self._model.transcribe_longform(str(source_path), fr_batch_size=self._batch_size)
        result_segments = [
            TranscriptionSegment(
                start=float(segment.start),
                end=float(segment.end),
                text=segment.text,
            )
            for segment in segments
        ]
        full_text = " ".join(segment.text.strip() for segment in result_segments).strip()
        return MeetingTranscription(
            model=self._model_name,
            source=source_path.name,
            text=full_text,
            segments=result_segments,
        )
