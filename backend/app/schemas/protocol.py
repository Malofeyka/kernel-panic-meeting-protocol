"""
Pydantic-схемы проекта протокола совещания и аналитического отчёта.

Принципы:
- каждое решение и поручение несёт цитату и таймкоды стенограммы (проверяемость, 0 галлюцинаций);
- отсутствующий исполнитель или срок — это `None` + пробел в аналитике, а не выдуманное значение;
- статус поручения вычисляется сервером по заполненности полей;
- элементы аналитики ссылаются на конкретные поручения (`action_item_ids`) и пункты повестки.
"""

import uuid
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.core.text import short_name

DATE_FORMAT = "%d.%m.%Y"


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def parse_ru_date(value: str) -> date:
    return datetime.strptime(value.strip(), DATE_FORMAT).date()


def format_ru_date(value: date) -> str:
    return value.strftime(DATE_FORMAT)


def _validate_optional_date(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    try:
        return format_ru_date(parse_ru_date(value))
    except ValueError as exc:
        raise ValueError("Дата должна быть в формате ДД.ММ.ГГГГ") from exc


class ItemOrigin(str, Enum):
    AI = "ai"  # извлечено ИИ-агентом и подтверждено цитатой
    MANUAL = "manual"  # добавлено или переписано секретарём


class ActionItemStatus(str, Enum):
    VALID = "valid"
    MISSING_DATE = "missing_date"
    MISSING_ASSIGNEE = "missing_assignee"
    MISSING_BOTH = "missing_assignee_and_date"


class Decision(BaseModel):
    id: str = Field(default_factory=lambda: new_id("dec"), description="Идентификатор решения")
    text: str = Field(..., min_length=1, description="Формулировка решения")
    quote: str | None = Field(None, description="Дословная цитата из стенограммы")
    source_start: float | None = Field(None, ge=0, description="Начало цитаты, сек")
    source_end: float | None = Field(None, ge=0, description="Конец цитаты, сек")
    origin: ItemOrigin = ItemOrigin.AI


class ActionItem(BaseModel):
    id: str = Field(default_factory=lambda: new_id("act"), description="Идентификатор поручения")
    task: str = Field(..., min_length=1, description="Формулировка поручения")
    assignee: str | None = Field(None, description="Ответственный (Фамилия И.О. или организация)")
    assignee_role: str | None = Field(None, description="Должность ответственного")
    assignee_raw: str | None = Field(None, description="Как исполнитель прозвучал в речи")
    due_date: str | None = Field(None, description="Срок исполнения ДД.ММ.ГГГГ")
    due_date_raw: str | None = Field(None, description="Как срок прозвучал в речи")
    is_recurring: bool = Field(False, description="Периодическое поручение (ежемесячно и т.п.)")
    status: ActionItemStatus = Field(
        ActionItemStatus.VALID, description="Вычисляется сервером по заполненности полей"
    )
    quote: str | None = Field(None, description="Дословная цитата из стенограммы")
    source_start: float | None = Field(None, ge=0, description="Начало цитаты, сек")
    source_end: float | None = Field(None, ge=0, description="Конец цитаты, сек")
    origin: ItemOrigin = ItemOrigin.AI

    @field_validator("due_date")
    @classmethod
    def _check_due_date(cls, value: str | None) -> str | None:
        return _validate_optional_date(value)

    @field_validator("assignee", "assignee_role", "assignee_raw", "due_date_raw", "quote")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None

    @model_validator(mode="after")
    def _compute_status(self) -> "ActionItem":
        has_date = self.due_date is not None or self.is_recurring
        has_assignee = self.assignee is not None
        if has_date and has_assignee:
            self.status = ActionItemStatus.VALID
        elif has_assignee:
            self.status = ActionItemStatus.MISSING_DATE
        elif has_date:
            self.status = ActionItemStatus.MISSING_ASSIGNEE
        else:
            self.status = ActionItemStatus.MISSING_BOTH
        return self


class AgendaItem(BaseModel):
    item_number: int = Field(..., ge=1, description="Номер пункта повестки")
    topic: str = Field(..., min_length=1, description="Тема вопроса")
    reporter: str | None = Field(None, description="Докладчик (СЛУШАЛИ)")
    decisions: list[Decision] = Field(default_factory=list, description="Принятые решения")
    action_items: list[ActionItem] = Field(default_factory=list, description="Поручения")


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class GapType(str, Enum):
    MISSING_DUE_DATE = "MISSING_DUE_DATE"
    VAGUE_DUE_DATE = "VAGUE_DUE_DATE"
    MISSING_ASSIGNEE = "MISSING_ASSIGNEE"
    AMBIGUOUS_ASSIGNEE = "AMBIGUOUS_ASSIGNEE"
    UNMATCHED_ASSIGNEE = "UNMATCHED_ASSIGNEE"
    NO_DECISION_FOR_AGENDA_ITEM = "NO_DECISION_FOR_AGENDA_ITEM"
    REJECTED_UNGROUNDED = "REJECTED_UNGROUNDED"
    UNPROCESSED_FRAGMENT = "UNPROCESSED_FRAGMENT"
    MISSING_INPUT = "MISSING_INPUT"


class GapIssue(BaseModel):
    type: GapType
    severity: Severity = Severity.MEDIUM
    description: str = Field(..., description="Описание выявленного пробела")
    agenda_item_number: int | None = Field(None, description="Пункт повестки")
    action_item_id: str | None = Field(None, description="Поручение, к которому относится пробел")
    context_quote: str | None = Field(None, description="Фрагмент стенограммы с контекстом")
    source_start: float | None = Field(None, ge=0, description="Таймкод фрагмента, сек")


class ContradictionScope(str, Enum):
    MEETING = "meeting"  # противоречие внутри текущего совещания
    ARCHIVE = "archive"  # расхождение с ранее принятыми протоколами


class Contradiction(BaseModel):
    id: str = Field(default_factory=lambda: new_id("con"))
    scope: ContradictionScope
    description: str
    action_item_ids: list[str] = Field(default_factory=list)
    quotes: list[str] = Field(
        default_factory=list, description="Цитаты, подтверждающие расхождение"
    )
    archive_reference: str | None = Field(None, description="Протокол и пункт из архива")


class RiskType(str, Enum):
    DEADLINE_IN_PAST = "DEADLINE_IN_PAST"
    TIGHT_DEADLINE = "TIGHT_DEADLINE"
    WEEKEND_DEADLINE = "WEEKEND_DEADLINE"
    ASSIGNEE_OVERLOAD = "ASSIGNEE_OVERLOAD"
    REPEATED_ASSIGNMENT = "REPEATED_ASSIGNMENT"
    DUPLICATE_ITEM = "DUPLICATE_ITEM"


class Risk(BaseModel):
    id: str = Field(default_factory=lambda: new_id("risk"))
    type: RiskType
    severity: Severity = Severity.MEDIUM
    description: str
    action_item_ids: list[str] = Field(default_factory=list)
    archive_reference: str | None = None


class AnalyticsReport(BaseModel):
    gaps: list[GapIssue] = Field(
        default_factory=list, description="Пробелы (нет срока/исполнителя)"
    )
    contradictions: list[Contradiction] = Field(
        default_factory=list, description="Противоречия в ходе встречи и с архивом"
    )
    risks: list[Risk] = Field(default_factory=list, description="Риски срыва исполнения")


class RevisionCycleState(BaseModel):
    current_cycle: int = Field(default=0, ge=0, description="Выполнено кругов ИИ-правок")
    max_cycles: int = Field(default=2, ge=0, description="Лимит кругов правок с участием ИИ")
    is_escalated_to_manual: bool = Field(
        default=False, description="Лимит исчерпан: доступна только ручная доработка"
    )


class Attendee(BaseModel):
    full_name: str = Field(..., min_length=1, description="ФИО как в списке участников")
    short_name: str = Field("", description="Фамилия И.О. (вычисляется, если не задано)")
    position: str | None = Field(None, description="Должность и организация")

    @model_validator(mode="after")
    def _fill_short_name(self) -> "Attendee":
        if not self.short_name.strip():
            self.short_name = short_name(self.full_name)
        return self


class ProtocolMetadata(BaseModel):
    meeting_title: str = Field("Аппаратное совещание", description="Наименование совещания")
    meeting_date: str = Field(..., description="Дата проведения (ДД.ММ.ГГГГ)")
    protocol_number: str | None = Field(None, description="Номер протокола")
    chairperson: str | None = Field(None, description="Председатель")
    secretary: str | None = Field(None, description="Секретарь")
    attendees: list[Attendee] = Field(default_factory=list, description="Присутствовали")

    @field_validator("meeting_date")
    @classmethod
    def _check_meeting_date(cls, value: str) -> str:
        validated = _validate_optional_date(value)
        if validated is None:
            raise ValueError("Дата совещания обязательна")
        return validated


class ProtocolDraft(BaseModel):
    session_id: str = Field(..., description="Идентификатор рабочей сессии")
    metadata: ProtocolMetadata
    agenda_items: list[AgendaItem] = Field(default_factory=list)
    analytics: AnalyticsReport = Field(default_factory=AnalyticsReport)
    revision_cycle: RevisionCycleState = Field(default_factory=RevisionCycleState)

    def iter_action_items(self) -> list[tuple[AgendaItem, int, ActionItem]]:
        """(пункт повестки, порядковый номер внутри пункта с учётом решений, поручение)."""
        result: list[tuple[AgendaItem, int, ActionItem]] = []
        for agenda_item in self.agenda_items:
            offset = len(agenda_item.decisions)
            for index, action in enumerate(agenda_item.action_items, start=offset + 1):
                result.append((agenda_item, index, action))
        return result

    def action_item_label(self, action_id: str) -> str:
        for agenda_item, index, action in self.iter_action_items():
            if action.id == action_id:
                return f"п. {agenda_item.item_number}.{index}"
        return action_id
