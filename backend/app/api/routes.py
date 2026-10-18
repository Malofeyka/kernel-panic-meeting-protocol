"""
Определение маршрутов API для протоколирования совещаний.
Полный API-контракт между Backend и Frontend.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from backend.app.schemas.api_contract import (
    ErrorDetail,
    ExportDocxResponse,
    ProcessingStep,
    RefineDraftRequest,
    RefineDraftResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionStatusResponse,
)
from backend.app.schemas.protocol import (
    AnalyticsReport,
    ProtocolDraft,
    ProtocolMetadata,
    RevisionCycleState,
)

router = APIRouter(prefix="/api/sessions", tags=["Сессии протоколирования"])

# Локальное in-memory хранилище сессий для контракта/моков
_SESSIONS_DB: dict[str, Any] = {}


@router.post(
    "/create",
    response_model=SessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="1. Создание новой рабочей сессии протоколирования",
)
async def create_session(
    request: SessionCreateRequest | None = None,
) -> SessionCreateResponse:
    session_id = str(uuid.uuid4())
    now_str = datetime.now(UTC).strftime("%d.%m.%Y")
    title = request.meeting_title if request and request.meeting_title else "Аппаратное совещание"
    date_str = request.meeting_date if request and request.meeting_date else now_str

    draft = ProtocolDraft(
        session_id=session_id,
        metadata=ProtocolMetadata(
            meeting_title=title,
            meeting_date=date_str,
            chairperson="Министр образования Свердловской области",
            secretary="Ответственный специалист секретариата",
            attendees=[],
        ),
        agenda_items=[],
        analytics=AnalyticsReport(),
        revision_cycle=RevisionCycleState(
            current_cycle=0, max_cycles=2, is_escalated_to_manual=False
        ),
    )

    _SESSIONS_DB[session_id] = {
        "status": ProcessingStep.IDLE,
        "progress": 0,
        "step_description": "Сессия создана. Ожидание загрузки файлов.",
        "draft": draft,
        "files": {},
    }

    return SessionCreateResponse(session_id=session_id, status=ProcessingStep.IDLE)


@router.post(
    "/{session_id}/upload",
    response_model=SessionStatusResponse,
    summary="2. Пакетная загрузка аудио и сопроводительных материалов",
)
async def upload_session_files(
    session_id: str,
    audio_file: UploadFile = File(..., description="Аудиозапись совещания (WAV, MP3, M4A)"),
    agenda_file: UploadFile | None = File(
        None, description="Повестка совещания (.docx, .pdf, .txt)"
    ),
    attendees_file: UploadFile | None = File(None, description="Список участников совещания"),
    template_file: UploadFile | None = File(
        None, description="Пользовательский шаблон протокола (.docx)"
    ),
    archive_files: list[UploadFile] | None = File(
        None, description="Архив предыдущих протоколов для сверки"
    ),
) -> SessionStatusResponse:
    if session_id not in _SESSIONS_DB:
        raise HTTPException(status_code=404, detail="Сессия не найдена")

    session = _SESSIONS_DB[session_id]
    session["status"] = ProcessingStep.TRANSCRIBING
    session["progress"] = 15
    session["step_description"] = (
        f"Файлы загружены. Запущена транскрибация аудиозаписи '{audio_file.filename}'..."
    )

    return SessionStatusResponse(
        session_id=session_id,
        status=session["status"],
        progress_percent=session["progress"],
        current_step_description=session["step_description"],
        error_message=None,
    )


@router.get(
    "/{session_id}/status",
    response_model=SessionStatusResponse,
    summary="3. Опрос прогресса обработки (STT -> NER/LLM -> Analytics)",
)
async def get_session_status(session_id: str) -> SessionStatusResponse:
    if session_id not in _SESSIONS_DB:
        raise HTTPException(status_code=404, detail="Сессия не найдена")

    session = _SESSIONS_DB[session_id]
    return SessionStatusResponse(
        session_id=session_id,
        status=session["status"],
        progress_percent=session["progress"],
        current_step_description=session["step_description"],
        error_message=None,
    )


@router.get(
    "/{session_id}/draft",
    response_model=ProtocolDraft,
    summary="4. Получение сформированного проекта протокола и аналитики",
)
async def get_session_draft(session_id: str) -> ProtocolDraft:
    if session_id not in _SESSIONS_DB:
        raise HTTPException(status_code=404, detail="Сессия не найдена")

    draft: ProtocolDraft = _SESSIONS_DB[session_id]["draft"]
    return draft


@router.post(
    "/{session_id}/refine",
    response_model=RefineDraftResponse,
    responses={
        400: {
            "model": ErrorDetail,
            "description": "Превышение лимита кругов автоматической генерации",
        }
    },
    summary="5. Внесение правок и запрос повторной генерации (до 2 кругов)",
)
async def refine_draft(session_id: str, request: RefineDraftRequest) -> RefineDraftResponse:
    if session_id not in _SESSIONS_DB:
        raise HTTPException(status_code=404, detail="Сессия не найдена")

    session = _SESSIONS_DB[session_id]
    draft: ProtocolDraft = session["draft"]
    cycle = draft.revision_cycle

    # Применение обновленных метаданных и пунктов повестки, если переданы
    if request.updated_metadata:
        draft.metadata = request.updated_metadata
    if request.updated_agenda_items:
        draft.agenda_items = request.updated_agenda_items

    if request.action == "ai_regenerate":
        # Проверка лимита кругов правок (<= 2)
        if cycle.current_cycle >= cycle.max_cycles:
            cycle.is_escalated_to_manual = True
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Превышен лимит автоматических кругов правок (максимум 2). Переключено в режим ручной доработки.",
            )

        cycle.current_cycle += 1
        msg = f"ИИ-агент успешно обновил проект протокола. Круг правок: {cycle.current_cycle} из {cycle.max_cycles}."
        if cycle.current_cycle >= cycle.max_cycles:
            cycle.is_escalated_to_manual = True
            msg += " Достигнут лимит автоматических генераций. Последующие правки вносятся вручную."
    else:
        # Ручное сохранение
        msg = "Правки успешно сохранены секретарем вручную (без расхода лимита генераций ИИ)."

    return RefineDraftResponse(
        session_id=session_id, updated_draft=draft, revision_cycle=cycle, message=msg
    )


@router.post(
    "/{session_id}/export",
    response_model=ExportDocxResponse,
    summary="6. Формирование и ссылка на скачивание Word-документа (.docx)",
)
async def export_protocol_docx(session_id: str) -> ExportDocxResponse:
    if session_id not in _SESSIONS_DB:
        raise HTTPException(status_code=404, detail="Сессия не найдена")

    file_name = f"Протокол_совещания_{session_id[:8]}.docx"
    return ExportDocxResponse(
        session_id=session_id,
        file_name=file_name,
        download_url=f"/api/sessions/{session_id}/download/{file_name}",
    )
