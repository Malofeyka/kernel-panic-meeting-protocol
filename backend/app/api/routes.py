"""
Маршруты API протоколирования совещаний (BE-101, BE-203, BE-102).
Полный API-контракт между Backend и Frontend: openspec/specs/api/spec.md.

Длительные операции (STT + LLM, ИИ-правка) выполняются в фоне:
эндпоинт сразу возвращает статус, фронтенд опрашивает GET /{id}/status.
"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse

from backend.app.api.dependencies import AppServices, get_services
from backend.app.persistence.session_store import SessionNotFoundError, UploadTooLargeError
from backend.app.schemas.api_contract import (
    BUSY_STEPS,
    ErrorDetail,
    ExportDocxResponse,
    ExportInfoResponse,
    ProcessingStep,
    RefineAction,
    RefineDraftRequest,
    RefineDraftResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionDetailsResponse,
    SessionStatusResponse,
    SessionSummary,
    UploadedFilesInfo,
)
from backend.app.schemas.protocol import (
    ProtocolDraft,
    ProtocolMetadata,
    RevisionCycleState,
    format_ru_date,
)
from backend.app.schemas.session import ExportInfo, SessionFiles, SessionRecord, StoredFile
from backend.app.schemas.transcription import MeetingTranscription
from backend.app.services.document_parser import SUPPORTED_DOCUMENT_SUFFIXES
from backend.app.services.docx_generator import DocxGenerationError

router = APIRouter(prefix="/api/sessions", tags=["Сессии протоколирования"])

ServicesDep = Annotated[AppServices, Depends(get_services)]

AUDIO_SUFFIXES = frozenset(
    {
        ".wav",
        ".mp3",
        ".m4a",
        ".ogg",
        ".flac",
        ".aac",
        ".wma",
        ".mp4",
        ".mkv",
        ".webm",
        ".mov",
        ".avi",
    }
)
TRANSCRIPT_SUFFIXES = frozenset({".json", *SUPPORTED_DOCUMENT_SUFFIXES})
TEMPLATE_SUFFIXES = frozenset({".docx"})
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
EXPORT_STORED_NAME = "protocol.docx"
LIMIT_EXCEEDED_MESSAGE = (
    "Превышен лимит автоматических кругов правок (максимум {max}). "
    "Переключено в режим ручной доработки."
)

_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorDetail, "description": "Сессия не найдена"},
    409: {"model": ErrorDetail, "description": "Сессия занята обработкой или не готова"},
}


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сессия не найдена")


def _get_record(services: AppServices, session_id: str) -> SessionRecord:
    try:
        return services.store.get(session_id)
    except SessionNotFoundError as exc:
        raise _not_found() from exc


def _ensure_not_busy(record: SessionRecord) -> None:
    if record.status in BUSY_STEPS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Сессия обрабатывается. Дождитесь завершения текущей операции.",
        )


def _status_response(record: SessionRecord) -> SessionStatusResponse:
    return SessionStatusResponse(
        session_id=record.session_id,
        status=record.status,
        progress_percent=record.progress,
        current_step_description=record.step_description,
        error_message=record.error_message,
        updated_at=record.updated_at,
    )


def _download_url(session_id: str) -> str:
    return f"/api/sessions/{session_id}/download"


def _present(upload: UploadFile | None) -> UploadFile | None:
    """Браузер может прислать пустое поле файла — считаем его отсутствующим."""
    if upload is None or not (upload.filename or "").strip():
        return None
    return upload


def _check_suffix(upload: UploadFile, allowed: frozenset[str], label: str) -> str:
    suffix = Path(upload.filename or "").suffix.casefold()
    if suffix not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"{label}: формат «{suffix or 'без расширения'}» не поддерживается. "
                f"Допустимые форматы: {', '.join(sorted(allowed))}."
            ),
        )
    return suffix


@router.get("", response_model=list[SessionSummary], summary="0. Список сессий")
def list_sessions(services: ServicesDep) -> list[SessionSummary]:
    return [
        SessionSummary(
            session_id=record.session_id,
            meeting_title=record.draft.metadata.meeting_title,
            meeting_date=record.draft.metadata.meeting_date,
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        for record in services.store.list()
    ]


@router.post(
    "/create",
    response_model=SessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="1. Создание новой рабочей сессии протоколирования",
)
def create_session(
    services: ServicesDep, request: SessionCreateRequest | None = None
) -> SessionCreateResponse:
    request = request or SessionCreateRequest()
    session_id = str(uuid.uuid4())
    meeting_date = request.meeting_date or format_ru_date(datetime.now().astimezone().date())
    draft = ProtocolDraft(
        session_id=session_id,
        metadata=ProtocolMetadata(
            meeting_title=request.meeting_title or "Аппаратное совещание",
            meeting_date=meeting_date,
            protocol_number=request.protocol_number,
            chairperson=request.chairperson,
            secretary=request.secretary,
        ),
        revision_cycle=RevisionCycleState(max_cycles=services.settings.max_revision_cycles),
    )
    record = SessionRecord(
        session_id=session_id,
        step_description="Сессия создана. Ожидание загрузки файлов.",
        draft=draft,
    )
    services.store.create(record)
    return SessionCreateResponse(
        session_id=session_id, status=record.status, created_at=record.created_at
    )


@router.get(
    "/{session_id}",
    response_model=SessionDetailsResponse,
    responses={404: _ERROR_RESPONSES[404]},
    summary="Полное состояние сессии (для восстановления экрана)",
)
def get_session(session_id: str, services: ServicesDep) -> SessionDetailsResponse:
    record = _get_record(services, session_id)
    files = record.files
    export = (
        ExportInfoResponse(
            file_name=record.export.file_name,
            download_url=_download_url(session_id),
            warnings=record.export.warnings,
            generated_at=record.export.generated_at,
        )
        if record.export
        else None
    )
    return SessionDetailsResponse(
        session_id=session_id,
        meeting_title=record.draft.metadata.meeting_title,
        meeting_date=record.draft.metadata.meeting_date,
        status=record.status,
        progress_percent=record.progress,
        current_step_description=record.step_description,
        error_message=record.error_message,
        has_draft=record.has_generated_draft,
        has_transcript=services.store.load_transcript(session_id) is not None,
        files=UploadedFilesInfo(
            audio=files.audio.original_name if files.audio else None,
            transcript=files.transcript.original_name if files.transcript else None,
            agenda=files.agenda.original_name if files.agenda else None,
            attendees=files.attendees.original_name if files.attendees else None,
            template=files.template.original_name if files.template else None,
            archive=[item.original_name for item in files.archive],
        ),
        export=export,
        input_warnings=record.context.warnings,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_ERROR_RESPONSES,
    summary="Удаление сессии со всеми файлами",
)
def delete_session(session_id: str, services: ServicesDep) -> Response:
    record = _get_record(services, session_id)
    _ensure_not_busy(record)
    services.store.delete(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{session_id}/upload",
    response_model=SessionStatusResponse,
    responses={
        400: {"model": ErrorDetail, "description": "Неверный формат или не хватает файлов"},
        413: {"model": ErrorDetail, "description": "Файл превышает допустимый размер"},
        **_ERROR_RESPONSES,
    },
    summary="2. Пакетная загрузка аудио и сопроводительных материалов (запускает обработку)",
)
def upload_session_files(
    session_id: str,
    services: ServicesDep,
    audio_file: UploadFile | None = File(
        None, description="Аудио/видеозапись совещания (WAV, MP3, M4A, OGG, FLAC, MP4…)"
    ),
    transcript_file: UploadFile | None = File(
        None,
        description="Готовая стенограмма вместо аудио (JSON GigaAM, TXT, DOCX, PDF)",
    ),
    agenda_file: UploadFile | None = File(None, description="Повестка (.docx, .pdf, .txt)"),
    attendees_file: UploadFile | None = File(None, description="Список участников"),
    template_file: UploadFile | None = File(None, description="Шаблон протокола (.docx)"),
    archive_files: list[UploadFile] | None = File(None, description="Предыдущие протоколы"),
) -> SessionStatusResponse:
    record = _get_record(services, session_id)
    _ensure_not_busy(record)

    audio, transcript = _present(audio_file), _present(transcript_file)
    agenda, attendees, template = (
        _present(agenda_file),
        _present(attendees_file),
        _present(template_file),
    )
    archive = [item for item in (archive_files or []) if _present(item) is not None]
    if audio is None and transcript is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Загрузите аудиозапись совещания (audio_file) или готовую стенограмму "
            "(transcript_file).",
        )

    planned: list[tuple[str, UploadFile, str]] = []
    if audio is not None:
        planned.append(("audio", audio, _check_suffix(audio, AUDIO_SUFFIXES, "Аудиозапись")))
    if transcript is not None:
        planned.append(
            (
                "transcript",
                transcript,
                _check_suffix(transcript, TRANSCRIPT_SUFFIXES, "Стенограмма"),
            )
        )
    if agenda is not None:
        planned.append(
            ("agenda", agenda, _check_suffix(agenda, SUPPORTED_DOCUMENT_SUFFIXES, "Повестка"))
        )
    if attendees is not None:
        planned.append(
            (
                "attendees",
                attendees,
                _check_suffix(attendees, SUPPORTED_DOCUMENT_SUFFIXES, "Список участников"),
            )
        )
    if template is not None:
        planned.append(
            ("template", template, _check_suffix(template, TEMPLATE_SUFFIXES, "Шаблон протокола"))
        )
    for index, item in enumerate(archive, start=1):
        suffix = _check_suffix(item, SUPPORTED_DOCUMENT_SUFFIXES, f"Архивный протокол {index}")
        planned.append((f"archive_{index}", item, suffix))

    store = services.store
    store.clear_files(session_id)
    files = SessionFiles()
    try:
        for kind, upload, suffix in planned:
            stored_name = f"{kind}{suffix}"
            size = store.save_upload(
                session_id, upload.file, stored_name, services.settings.max_upload_bytes
            )
            stored = StoredFile(
                original_name=upload.filename or stored_name,
                stored_name=stored_name,
                size_bytes=size,
            )
            if kind.startswith("archive_"):
                files.archive.append(stored)
            else:
                setattr(files, kind, stored)
    except UploadTooLargeError as exc:
        store.clear_files(session_id)

        def reset_files(item: SessionRecord) -> None:
            item.files = SessionFiles()
            item.status = ProcessingStep.IDLE
            item.error_message = None

        store.update(session_id, reset_files)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Файл превышает допустимый размер {services.settings.max_upload_mb} МБ.",
        ) from exc

    def queue(item: SessionRecord) -> None:
        item.files = files
        item.draft = ProtocolDraft(
            session_id=session_id,
            metadata=item.draft.metadata,
            revision_cycle=RevisionCycleState(max_cycles=services.settings.max_revision_cycles),
        )
        item.has_generated_draft = False
        item.pipeline_notes = []
        item.export = None
        item.status = ProcessingStep.TRANSCRIBING
        item.progress = 1
        item.error_message = None
        source = audio.filename if audio is not None else transcript.filename if transcript else ""
        item.step_description = f"Файлы загружены. Запущена обработка «{source}»…"

    store.update(session_id, queue)
    services.runner.submit(lambda: services.pipeline.process(session_id))
    return _status_response(store.get(session_id))


@router.post(
    "/{session_id}/process",
    response_model=SessionStatusResponse,
    responses={400: {"model": ErrorDetail}, **_ERROR_RESPONSES},
    summary="Повторный запуск обработки по уже загруженным файлам (после ошибки)",
)
def restart_processing(session_id: str, services: ServicesDep) -> SessionStatusResponse:
    record = _get_record(services, session_id)
    _ensure_not_busy(record)
    if record.files.audio is None and record.files.transcript is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нет загруженной аудиозаписи или стенограммы — выполните загрузку файлов.",
        )

    def queue(item: SessionRecord) -> None:
        item.status = ProcessingStep.TRANSCRIBING
        item.progress = 1
        item.error_message = None
        item.step_description = "Повторный запуск обработки…"

    services.store.update(session_id, queue)
    services.runner.submit(lambda: services.pipeline.process(session_id))
    return _status_response(services.store.get(session_id))


@router.get(
    "/{session_id}/status",
    response_model=SessionStatusResponse,
    responses={404: _ERROR_RESPONSES[404]},
    summary="3. Опрос прогресса обработки (STT -> NER/LLM -> Analytics)",
)
def get_session_status(session_id: str, services: ServicesDep) -> SessionStatusResponse:
    return _status_response(_get_record(services, session_id))


@router.get(
    "/{session_id}/draft",
    response_model=ProtocolDraft,
    responses={404: _ERROR_RESPONSES[404]},
    summary="4. Получение сформированного проекта протокола и аналитики",
)
def get_session_draft(session_id: str, services: ServicesDep) -> ProtocolDraft:
    return _get_record(services, session_id).draft


@router.get(
    "/{session_id}/transcript",
    response_model=MeetingTranscription,
    responses={404: {"model": ErrorDetail, "description": "Сессия или стенограмма не найдена"}},
    summary="Стенограмма с таймкодами (левая панель редактора)",
)
def get_session_transcript(session_id: str, services: ServicesDep) -> MeetingTranscription:
    _get_record(services, session_id)
    transcription = services.store.load_transcript(session_id)
    if transcription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Стенограмма ещё не сформирована"
        )
    return transcription


@router.post(
    "/{session_id}/refine",
    response_model=RefineDraftResponse,
    responses={
        400: {
            "model": ErrorDetail,
            "description": "Превышение лимита кругов автоматической генерации",
        },
        **_ERROR_RESPONSES,
    },
    summary="5. Внесение правок и запрос повторной генерации (до 2 кругов)",
)
def refine_draft(
    session_id: str, request: RefineDraftRequest, services: ServicesDep
) -> RefineDraftResponse:
    record = _get_record(services, session_id)
    _ensure_not_busy(record)

    draft = record.draft.model_copy(deep=True)
    if request.updated_metadata is not None:
        draft.metadata = request.updated_metadata
    if request.updated_agenda_items is not None:
        draft.agenda_items = request.updated_agenda_items
    draft.session_id = session_id
    cycle = draft.revision_cycle

    if request.action == RefineAction.AI_REGENERATE:
        feedback = (request.user_feedback or "").strip()
        if cycle.current_cycle >= cycle.max_cycles:
            cycle.is_escalated_to_manual = True
            draft.analytics = services.pipeline.analyze(record, draft)

            def keep_edits(item: SessionRecord) -> None:
                item.draft = draft
                item.export = None

            services.store.update(session_id, keep_edits)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=LIMIT_EXCEEDED_MESSAGE.format(max=cycle.max_cycles),
            )
        if not record.has_generated_draft:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Проект протокола ещё не сформирован — ИИ-правка недоступна.",
            )
        if not feedback:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Опишите замечания для ИИ-агента в поле user_feedback.",
            )
        cycle.current_cycle += 1
        cycle.is_escalated_to_manual = cycle.current_cycle >= cycle.max_cycles
        draft.analytics = services.pipeline.analyze(record, draft)

        def start_refine(item: SessionRecord) -> None:
            item.draft = draft
            item.export = None
            item.status = ProcessingStep.REFINING
            item.progress = 50
            item.error_message = None
            item.step_description = (
                f"ИИ-агент вносит правки (круг {cycle.current_cycle} из {cycle.max_cycles})…"
            )

        services.store.update(session_id, start_refine)
        services.runner.submit(lambda: services.pipeline.refine(session_id, feedback))
        current = services.store.get(session_id)
        message = (
            current.step_description
            if current.status != ProcessingStep.REFINING
            else "ИИ-правка запущена. Опрашивайте /status до статуса ready, затем загрузите /draft."
        )
        if current.error_message:
            message = current.error_message
        return RefineDraftResponse(
            session_id=session_id,
            status=current.status,
            updated_draft=current.draft,
            revision_cycle=current.draft.revision_cycle,
            message=message,
        )

    draft.analytics = services.pipeline.analyze(record, draft)

    def manual_save(item: SessionRecord) -> None:
        item.draft = draft
        item.export = None
        item.error_message = None

    services.store.update(session_id, manual_save)
    return RefineDraftResponse(
        session_id=session_id,
        status=record.status,
        updated_draft=draft,
        revision_cycle=draft.revision_cycle,
        message="Правки успешно сохранены секретарем вручную (без расхода лимита генераций ИИ).",
    )


@router.post(
    "/{session_id}/export",
    response_model=ExportDocxResponse,
    responses=_ERROR_RESPONSES,
    summary="6. Формирование и ссылка на скачивание Word-документа (.docx)",
)
def export_protocol_docx(session_id: str, services: ServicesDep) -> ExportDocxResponse:
    record = _get_record(services, session_id)
    _ensure_not_busy(record)
    template = (
        services.store.files_dir(session_id) / record.files.template.stored_name
        if record.files.template
        else None
    )
    output = services.store.export_dir(session_id) / EXPORT_STORED_NAME
    try:
        warnings = services.docx.render(record.draft, output, template)
    except DocxGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    meeting_date = record.draft.metadata.meeting_date
    file_name = f"Протокол_совещания_{meeting_date}_{session_id[:8]}.docx"
    export = ExportInfo(file_name=file_name, stored_name=EXPORT_STORED_NAME, warnings=warnings)

    def save_export(item: SessionRecord) -> None:
        item.export = export

    services.store.update(session_id, save_export)
    return ExportDocxResponse(
        session_id=session_id,
        file_name=file_name,
        download_url=_download_url(session_id),
        warnings=warnings,
        generated_at=export.generated_at,
    )


@router.get(
    "/{session_id}/download",
    response_class=FileResponse,
    responses={404: {"model": ErrorDetail, "description": "Документ ещё не сформирован"}},
    summary="7. Скачивание сформированного протокола (.docx)",
)
def download_protocol_docx(session_id: str, services: ServicesDep) -> FileResponse:
    record = _get_record(services, session_id)
    path = services.store.export_dir(session_id) / EXPORT_STORED_NAME
    if record.export is None or not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Документ ещё не сформирован — выполните POST /export.",
        )
    return FileResponse(path, media_type=DOCX_MEDIA_TYPE, filename=record.export.file_name)
