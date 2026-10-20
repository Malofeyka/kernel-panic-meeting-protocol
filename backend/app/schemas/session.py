"""Внутренняя модель рабочей сессии, хранимая на диске (не часть публичного API)."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from backend.app.schemas.api_contract import ProcessingStep
from backend.app.schemas.documents import MeetingContext
from backend.app.schemas.protocol import GapIssue, ProtocolDraft


class StoredFile(BaseModel):
    original_name: str
    stored_name: str
    size_bytes: int


class SessionFiles(BaseModel):
    audio: StoredFile | None = None
    transcript: StoredFile | None = None
    agenda: StoredFile | None = None
    attendees: StoredFile | None = None
    template: StoredFile | None = None
    archive: list[StoredFile] = Field(default_factory=list)


class ExportInfo(BaseModel):
    file_name: str
    stored_name: str
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SessionRecord(BaseModel):
    session_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: ProcessingStep = ProcessingStep.IDLE
    progress: int = Field(0, ge=0, le=100)
    step_description: str = ""
    error_message: str | None = None
    files: SessionFiles = Field(default_factory=SessionFiles)
    context: MeetingContext = Field(default_factory=MeetingContext)
    draft: ProtocolDraft
    has_generated_draft: bool = Field(False, description="Черновик уже сформирован пайплайном")
    pipeline_notes: list[GapIssue] = Field(
        default_factory=list,
        description="Пробелы, выявленные при обработке (отклонённые пункты, сбойные фрагменты)",
    )
    export: ExportInfo | None = None

    def refund_revision_cycle(self) -> None:
        """Возврат круга правок, если ИИ-правка не была выполнена."""
        cycle = self.draft.revision_cycle
        cycle.current_cycle = max(0, cycle.current_cycle - 1)
        cycle.is_escalated_to_manual = cycle.current_cycle >= cycle.max_cycles
