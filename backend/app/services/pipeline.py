"""Оркестратор обработки сессии: материалы -> STT -> извлечение -> сверка -> проект.

Выполняется в фоновом потоке (см. ThreadJobRunner); прогресс и ошибки пишутся
в хранилище, фронтенд опрашивает GET /api/sessions/{id}/status.
"""

from collections.abc import Callable

from backend.app.core.config import Settings
from backend.app.persistence.session_store import SessionStore
from backend.app.schemas.api_contract import ProcessingStep
from backend.app.schemas.documents import MeetingContext
from backend.app.schemas.protocol import (
    AnalyticsReport,
    ProtocolDraft,
    ProtocolMetadata,
    RevisionCycleState,
    parse_ru_date,
)
from backend.app.schemas.session import SessionRecord
from backend.app.schemas.transcription import DomainVocabulary, MeetingTranscription
from backend.app.services.analytics import AnalyticsEngine
from backend.app.services.attendee_matcher import AttendeeMatcher
from backend.app.services.document_parser import (
    DocumentParseError,
    extract_text,
    parse_agenda,
    parse_archive_protocol,
    parse_attendees,
)
from backend.app.services.extraction import ProtocolExtractor
from backend.app.services.gigachat_client import GigaChatUnavailableError
from backend.app.services.interfaces import LLMClient, Transcriber
from backend.app.services.protocol_builder import ProtocolBuilder
from backend.app.services.refinement import DraftRefiner
from backend.app.services.transcript import TranscriptIndex, ensure_segments, load_transcript_file

DEFAULT_ABBREVIATIONS = [
    "ОГЭ", "ЕГЭ", "ГИА", "ВПР", "ИРО", "ФОП", "ФГОС", "ППЭ", "КИМ", "ОВЗ", "СПО", "РИП",
]  # fmt: skip


class PipelineError(RuntimeError):
    pass


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, GigaChatUnavailableError):
        return (
            "Локальная модель GigaChat недоступна. Запустите llama-server "
            f"(scripts/start_gigachat.ps1) и нажмите «Повторить». Подробности: {exc}"
        )
    if isinstance(exc, (PipelineError, DocumentParseError)):
        return str(exc)
    return f"Ошибка обработки: {exc}"


def build_vocabulary(context: MeetingContext) -> DomainVocabulary:
    return DomainVocabulary(
        people=[attendee.full_name for attendee in context.attendees],
        positions=[attendee.position for attendee in context.attendees if attendee.position],
        abbreviations=DEFAULT_ABBREVIATIONS,
    )


class ProcessingPipeline:
    def __init__(
        self,
        store: SessionStore,
        settings: Settings,
        transcriber_factory: Callable[[], Transcriber],
        llm_factory: Callable[[], LLMClient],
    ) -> None:
        self._store = store
        self._settings = settings
        self._transcriber_factory = transcriber_factory
        self._llm_factory = llm_factory
        self._analytics = AnalyticsEngine(settings)

    # --- служебное ---
    def _status(
        self, session_id: str, status: ProcessingStep, progress: int, description: str
    ) -> None:
        def mutate(record: SessionRecord) -> None:
            record.status = status
            record.progress = progress
            record.step_description = description
            record.error_message = None

        self._store.update(session_id, mutate)

    def build_context(self, record: SessionRecord) -> MeetingContext:
        files_dir = self._store.files_dir(record.session_id)
        context = MeetingContext()

        def read(stored_name: str, original: str) -> str | None:
            try:
                return extract_text(files_dir / stored_name)
            except DocumentParseError as exc:
                context.warnings.append(f"Файл «{original}» не разобран: {exc}")
                return None

        if record.files.attendees:
            text = read(record.files.attendees.stored_name, record.files.attendees.original_name)
            if text is not None:
                attendees, chair, secretary = parse_attendees(text)
                context.attendees, context.chairperson, context.secretary = (
                    attendees,
                    chair,
                    secretary,
                )
                if not attendees:
                    context.warnings.append(
                        f"В файле «{record.files.attendees.original_name}» не найдено ни одного "
                        "ФИО (ожидается «Фамилия Имя Отчество — должность» по строкам)."
                    )
        if record.files.agenda:
            text = read(record.files.agenda.stored_name, record.files.agenda.original_name)
            if text is not None:
                context.agenda = parse_agenda(text)
                if not context.agenda:
                    context.warnings.append(
                        f"В повестке «{record.files.agenda.original_name}» не найдено вопросов."
                    )
        for archive_file in record.files.archive:
            text = read(archive_file.stored_name, archive_file.original_name)
            if text is not None:
                context.archive.append(parse_archive_protocol(text, archive_file.original_name))
        return context

    def load_transcription(
        self, record: SessionRecord, context: MeetingContext
    ) -> MeetingTranscription:
        cached = self._store.load_transcript(record.session_id)
        if cached is not None:
            return cached
        files_dir = self._store.files_dir(record.session_id)
        if record.files.transcript is not None:
            transcription = load_transcript_file(
                files_dir / record.files.transcript.stored_name,
                record.files.transcript.original_name,
            )
        elif record.files.audio is not None:
            transcriber = self._transcriber_factory()
            transcription = transcriber.transcribe(
                files_dir / record.files.audio.stored_name, vocabulary=build_vocabulary(context)
            )
            transcription = transcription.model_copy(
                update={"source": record.files.audio.original_name}
            )
        else:
            raise PipelineError("Не загружены ни аудиозапись, ни стенограмма совещания.")
        transcription = ensure_segments(transcription)
        if not transcription.segments:
            raise PipelineError("Стенограмма пуста: речь в аудиозаписи не распознана.")
        self._store.save_transcript(record.session_id, transcription)
        return transcription

    def analyze(self, record: SessionRecord, draft: ProtocolDraft) -> AnalyticsReport:
        return self._analytics.analyze(
            draft,
            archive=record.context.archive,
            matcher=AttendeeMatcher(draft.metadata.attendees),
            pipeline_notes=record.pipeline_notes,
            input_warnings=record.context.warnings,
        )

    # --- первичная генерация ---
    def process(self, session_id: str) -> None:
        try:
            self._process(session_id)
        except Exception as exc:  # noqa: BLE001 — фоновая задача: ошибка должна попасть в статус
            message = _friendly_error(exc)

            def fail(record: SessionRecord) -> None:
                record.status = ProcessingStep.FAILED
                record.error_message = message
                record.step_description = "Обработка остановлена из-за ошибки."

            self._store.update(session_id, fail)

    def _process(self, session_id: str) -> None:
        self._status(session_id, ProcessingStep.TRANSCRIBING, 5, "Разбор сопутствующих материалов…")
        record = self._store.get(session_id)
        context = self.build_context(record)

        def save_context(item: SessionRecord) -> None:
            item.context = context

        record = self._store.update(session_id, save_context)

        has_cache = self._store.load_transcript(session_id) is not None
        description = (
            "Загрузка стенограммы…"
            if has_cache or record.files.transcript
            else "Распознавание речи (GigaAM). Для записи 1–1,5 ч это может занять до часа…"
        )
        self._status(session_id, ProcessingStep.TRANSCRIBING, 10, description)
        transcription = self.load_transcription(record, context)

        self._status(
            session_id, ProcessingStep.EXTRACTING, 50, "Подключение к локальной модели GigaChat…"
        )
        llm = self._llm_factory()
        llm.health()

        def progress(done: int, total: int) -> None:
            self._status(
                session_id,
                ProcessingStep.EXTRACTING,
                50 + 35 * done // max(total, 1),
                f"Извлечение решений и поручений: фрагмент {done} из {total}…",
            )

        extraction = ProtocolExtractor(llm, self._settings).extract(
            transcription, context, record.draft.metadata.meeting_date, on_progress=progress
        )

        self._status(
            session_id, ProcessingStep.CROSS_CHECKING, 90, "Сверка с участниками и архивом…"
        )
        record = self._store.get(session_id)
        meta = record.draft.metadata
        metadata = ProtocolMetadata(
            meeting_title=meta.meeting_title,
            meeting_date=meta.meeting_date,
            protocol_number=meta.protocol_number,
            chairperson=meta.chairperson or context.chairperson,
            secretary=meta.secretary or context.secretary,
            attendees=context.attendees,
        )
        index = TranscriptIndex(transcription)
        builder = ProtocolBuilder(
            index,
            AttendeeMatcher(context.attendees),
            parse_ru_date(meta.meeting_date),
            self._settings,
        )
        built = builder.build(extraction, context)
        draft = ProtocolDraft(
            session_id=session_id,
            metadata=metadata,
            agenda_items=built.agenda_items,
            revision_cycle=RevisionCycleState(max_cycles=self._settings.max_revision_cycles),
        )

        def finish(item: SessionRecord) -> None:
            item.pipeline_notes = built.notes
            item.draft = draft
            item.draft.analytics = self.analyze(item, draft)
            item.has_generated_draft = True
            item.export = None
            item.status = ProcessingStep.READY
            item.progress = 100
            item.error_message = None
            actions = len(draft.iter_action_items())
            item.step_description = (
                f"Проект протокола готов к вычитке: вопросов — {len(draft.agenda_items)}, "
                f"поручений — {actions}, замечаний аналитики — {len(item.draft.analytics.gaps)}."
            )

        self._store.update(session_id, finish)

    # --- ИИ-правка ---
    def refine(self, session_id: str, feedback: str) -> None:
        try:
            self._refine(session_id, feedback)
        except Exception as exc:  # noqa: BLE001 — откат круга правок при любой ошибке
            message = _friendly_error(exc)

            def rollback(record: SessionRecord) -> None:
                record.refund_revision_cycle()
                record.status = ProcessingStep.READY
                record.progress = 100
                record.error_message = (
                    f"ИИ-правка не выполнена, круг правок не израсходован. {message}"
                )
                record.step_description = "Проект протокола не изменён."

            self._store.update(session_id, rollback)

    def _refine(self, session_id: str, feedback: str) -> None:
        record = self._store.get(session_id)
        transcription = self._store.load_transcript(session_id)
        if transcription is None:
            raise PipelineError("Стенограмма сессии не найдена — выполните обработку заново.")
        llm = self._llm_factory()
        llm.health()
        attendees = record.draft.metadata.attendees
        matcher = AttendeeMatcher(attendees)
        meeting_date = parse_ru_date(record.draft.metadata.meeting_date)
        index = TranscriptIndex(transcription)
        builder = ProtocolBuilder(index, matcher, meeting_date, self._settings)
        refiner = DraftRefiner(llm, builder, index, matcher, meeting_date, self._settings)
        outcome = refiner.refine(record.draft, feedback)

        def apply(item: SessionRecord) -> None:
            cycle = item.draft.revision_cycle
            outcome.draft.revision_cycle = cycle
            item.draft = outcome.draft
            item.draft.analytics = self.analyze(item, item.draft)
            item.export = None
            item.status = ProcessingStep.READY
            item.progress = 100
            item.error_message = None
            summary = "; ".join(outcome.applied) if outcome.applied else "изменений не внесено"
            text = f"ИИ-правка выполнена (круг {cycle.current_cycle} из {cycle.max_cycles}): {summary}."
            if outcome.rejected:
                text += f" Не применено: {'; '.join(outcome.rejected)}."
            if cycle.is_escalated_to_manual:
                text += " Лимит ИИ-правок исчерпан — дальнейшие правки вносятся вручную."
            item.step_description = text

        self._store.update(session_id, apply)
