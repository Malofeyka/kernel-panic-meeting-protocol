"""
Полный API-контракт: схемы запросов и ответов для всех эндпоинтов системы.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from backend.app.schemas.protocol import (
    AgendaItem,
    ProtocolDraft,
    ProtocolMetadata,
    RevisionCycleState,
    format_ru_date,
    parse_ru_date,
)


class ProcessingStep(str, Enum):
    IDLE = "idle"
    UPLOADING = "uploading"
    TRANSCRIBING = "transcribing"  # STT распознавание речи
    EXTRACTING = "extracting"  # LLM извлечение сущностей
    CROSS_CHECKING = "cross_checking"  # Аналитика пробелов и архива
    READY = "ready"  # Проект готов к вычитке
    REFINING = "refining"  # Повторная генерация правок
    FAILED = "failed"  # Ошибка обработки


BUSY_STEPS = frozenset(
    {
        ProcessingStep.UPLOADING,
        ProcessingStep.TRANSCRIBING,
        ProcessingStep.EXTRACTING,
        ProcessingStep.CROSS_CHECKING,
        ProcessingStep.REFINING,
    }
)


# --- 1. Создание сессии ---
class SessionCreateRequest(BaseModel):
    meeting_title: str | None = Field("Аппаратное совещание", description="Наименование совещания")
    meeting_date: str | None = Field(
        None, description="Дата совещания ДД.ММ.ГГГГ (по умолчанию текущая дата)"
    )
    protocol_number: str | None = Field(None, description="Номер протокола")
    chairperson: str | None = Field(None, description="Председатель (если известен заранее)")
    secretary: str | None = Field(None, description="Секретарь (если известен заранее)")

    @field_validator("meeting_date")
    @classmethod
    def _check_date(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        try:
            return format_ru_date(parse_ru_date(value))
        except ValueError as exc:
            raise ValueError("Дата совещания должна быть в формате ДД.ММ.ГГГГ") from exc


class SessionCreateResponse(BaseModel):
    session_id: str = Field(..., description="UUID созданной сессии")
    status: ProcessingStep = Field(ProcessingStep.IDLE, description="Текущий статус сессии")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SessionSummary(BaseModel):
    session_id: str
    meeting_title: str
    meeting_date: str
    status: ProcessingStep
    created_at: datetime
    updated_at: datetime


class UploadedFilesInfo(BaseModel):
    audio: str | None = Field(None, description="Имя загруженной аудио/видеозаписи")
    transcript: str | None = Field(None, description="Имя загруженной готовой стенограммы")
    agenda: str | None = None
    attendees: str | None = None
    template: str | None = None
    archive: list[str] = Field(default_factory=list)


class ExportInfoResponse(BaseModel):
    file_name: str
    download_url: str
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime


class SessionDetailsResponse(BaseModel):
    """Полное состояние сессии — для восстановления экрана после перезагрузки страницы."""

    session_id: str
    meeting_title: str
    meeting_date: str
    status: ProcessingStep
    progress_percent: int
    current_step_description: str
    error_message: str | None = None
    has_draft: bool = Field(
        ..., description="Проект протокола сформирован (можно открыть редактор)"
    )
    has_transcript: bool
    files: UploadedFilesInfo
    export: ExportInfoResponse | None = None
    input_warnings: list[str] = Field(
        default_factory=list, description="Замечания разбора повестки/участников/архива"
    )
    created_at: datetime
    updated_at: datetime


# --- 2. Статус сессии ---
class SessionStatusResponse(BaseModel):
    session_id: str
    status: ProcessingStep
    progress_percent: int = Field(0, ge=0, le=100, description="Процент завершения от 0 до 100")
    current_step_description: str = Field("", description="Человекопонятное описание текущего шага")
    error_message: str | None = Field(None, description="Текст ошибки при статусе failed")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# --- 3. Повторная генерация / правки (Refinement Loop) ---
class RefineAction(str, Enum):
    AI_REGENERATE = "ai_regenerate"  # Запрос на перегенерацию с помощью LLM (до 2 раз)
    MANUAL_SAVE = "manual_save"  # Ручное сохранение изменений без вызова нейросети


class RefineDraftRequest(BaseModel):
    action: RefineAction = Field(RefineAction.AI_REGENERATE, description="Тип применения правок")
    user_feedback: str | None = Field(
        None, description="Текстовый комментарий секретаря к правкам для ИИ-агента"
    )
    updated_metadata: ProtocolMetadata | None = None
    updated_agenda_items: list[AgendaItem] | None = None


class RefineDraftResponse(BaseModel):
    session_id: str
    status: ProcessingStep = Field(
        ProcessingStep.READY,
        description="refining — ИИ-правка выполняется в фоне, опрашивайте /status",
    )
    updated_draft: ProtocolDraft
    revision_cycle: RevisionCycleState
    message: str = Field(..., description="Сообщение о результате операции")


# --- 4. Экспорт документа ---
class ExportDocxResponse(BaseModel):
    session_id: str
    file_name: str
    download_url: str
    warnings: list[str] = Field(default_factory=list, description="Замечания по шаблону")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# --- 5. Ошибки ---
class ErrorDetail(BaseModel):
    code: str = Field(..., description="Машиночитаемый код ошибки")
    message: str = Field(..., description="Понятное описание ошибки")
    details: dict[str, Any] | None = None
