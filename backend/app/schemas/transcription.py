from pydantic import BaseModel, Field


class TranscriptionSegment(BaseModel):
    start: float = Field(..., ge=0, description="Начало фрагмента в секундах")
    end: float = Field(..., ge=0, description="Конец фрагмента в секундах")
    text: str = Field(..., description="Распознанный текст фрагмента")


class MeetingTranscription(BaseModel):
    model: str = Field(..., description="Идентификатор локальной STT-модели")
    source: str = Field(..., description="Имя исходного аудио- или видеофайла")
    text: str = Field(..., description="Полный текст для передачи в локальную LLM")
    segments: list[TranscriptionSegment] = Field(
        default_factory=list, description="Фрагменты стенограммы с таймкодами"
    )
