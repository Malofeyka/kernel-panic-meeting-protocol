"""
Полный API-контракт: схемы запросов и ответов для всех эндпоинтов системы.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from backend.app.schemas.protocol import (
    AgendaItem,
    ProtocolDraft,
    ProtocolMetadata,
    RevisionCycleState,
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


# --- 1. Создание сессии ---
class SessionCreateRequest(BaseModel):
    meeting_title: str | None = Field("Аппаратное совещание", description="Наименование совещания")
    meeting_date: str | None = Field(
        None, description="Дата совещания (по умолчанию текущая дата ДД.ММ.ГГГГ)"
    )


class SessionCreateResponse(BaseModel):
    session_id: str = Field(..., description="UUID созданной сессии")
    status: ProcessingStep = Field(ProcessingStep.IDLE, description="Текущий статус сессии")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


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
    updated_draft: ProtocolDraft
    revision_cycle: RevisionCycleState
    message: str = Field(..., description="Сообщение о результате операции")


# --- 4. Экспорт документа ---
class ExportDocxResponse(BaseModel):
    session_id: str
    file_name: str
    download_url: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# --- 5. Ошибки ---
class ErrorDetail(BaseModel):
    code: str = Field(..., description="Машиночитаемый код ошибки")
    message: str = Field(..., description="Понятное описание ошибки")
    details: dict[str, Any] | None = None
