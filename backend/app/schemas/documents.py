"""Структуры, извлечённые из сопутствующих материалов (повестка, участники, архив)."""

from pydantic import BaseModel, Field

from backend.app.schemas.protocol import Attendee


class AgendaTopic(BaseModel):
    number: int = Field(..., ge=1)
    title: str = Field(..., min_length=1)
    reporter: str | None = None


class ArchiveActionItem(BaseModel):
    item_label: str | None = Field(None, description="Номер пункта в архивном протоколе")
    task: str
    assignee: str | None = None
    due_date: str | None = Field(None, description="ДД.ММ.ГГГГ")
    is_recurring: bool = False


class ArchiveProtocol(BaseModel):
    file_name: str
    protocol_number: str | None = None
    protocol_date: str | None = Field(None, description="ДД.ММ.ГГГГ")
    action_items: list[ArchiveActionItem] = Field(default_factory=list)

    @property
    def label(self) -> str:
        parts = ["Протокол"]
        if self.protocol_number:
            parts.append(f"№ {self.protocol_number}")
        if self.protocol_date:
            parts.append(f"от {self.protocol_date}")
        if len(parts) == 1:
            parts.append(f"«{self.file_name}»")
        return " ".join(parts)


class MeetingContext(BaseModel):
    attendees: list[Attendee] = Field(default_factory=list)
    chairperson: str | None = None
    secretary: str | None = None
    agenda: list[AgendaTopic] = Field(default_factory=list)
    archive: list[ArchiveProtocol] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list, description="Проблемы разбора файлов")
