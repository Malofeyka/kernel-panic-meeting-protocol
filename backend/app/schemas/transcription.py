from pydantic import BaseModel, Field, field_validator


class DomainVocabulary(BaseModel):
    people: list[str] = Field(default_factory=list, description="ФИО участников совещания")
    positions: list[str] = Field(default_factory=list, description="Должности участников")
    organizations: list[str] = Field(default_factory=list, description="Организации и учреждения")
    abbreviations: list[str] = Field(
        default_factory=list, description="Аббревиатуры предметной области"
    )
    terms: list[str] = Field(default_factory=list, description="Термины и фразы повестки")

    @field_validator("people", "positions", "organizations", "abbreviations", "terms")
    @classmethod
    def normalize_entries(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for entry in value:
            cleaned = " ".join(entry.split())
            key = cleaned.casefold()
            if not cleaned or key in seen:
                continue
            normalized.append(cleaned)
            seen.add(key)
        return normalized


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
