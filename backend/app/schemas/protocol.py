"""
Pydantic-схемы для протоколирования совещаний.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class ActionItem(BaseModel):
    id: str = Field(..., description="Уникальный идентификатор поручения")
    task: str = Field(..., description="Формулировка поручения")
    assignee: str = Field(..., description="Ответственное лицо (ФИО)")
    assignee_role: Optional[str] = Field(None, description="Должность ответственного лица")
    due_date: Optional[str] = Field(None, description="Срок исполнения в формате ДД.ММ.ГГГГ")
    status: str = Field("valid", description="Статус поручения: valid / missing_date / missing_assignee")
    quote: Optional[str] = Field(None, description="Цитата из стенограммы, на основе которой сформировано поручение")


class AgendaItem(BaseModel):
    item_number: int = Field(..., description="Номер пункта повестки")
    topic: str = Field(..., description="Тема вопроса")
    reporter: Optional[str] = Field(None, description="Докладчик")
    decisions: List[str] = Field(default_factory=list, description="Список принятых решений")
    action_items: List[ActionItem] = Field(default_factory=list, description="Список поручений по пункту")


class GapIssue(BaseModel):
    type: str = Field(..., description="Тип пробела: MISSING_DUE_DATE / MISSING_ASSIGNEE")
    description: str = Field(..., description="Описание выявленного пробела")
    context_quote: Optional[str] = Field(None, description="Фрагмент стенограммы с контекстом")


class AnalyticsReport(BaseModel):
    gaps: List[GapIssue] = Field(default_factory=list, description="Пробелы в протоколе")
    contradictions: List[str] = Field(default_factory=list, description="Противоречия с архивными протоколами или в ходе встречи")
    risks: List[str] = Field(default_factory=list, description="Риски срыва сроков или неисполнения")


class RevisionCycleState(BaseModel):
    current_cycle: int = Field(1, description="Текущий круг правок (1 или 2)")
    max_cycles: int = Field(2, description="Максимально допустимое количество кругов правок с участием ИИ")
    is_escalated_to_manual: bool = Field(False, description="Флаг перехода в режим ручной доработки при превышении лимита")


class ProtocolMetadata(BaseModel):
    meeting_title: str = Field("Аппаратное совещание", description="Наименование совещания")
    meeting_date: str = Field(..., description="Дата проведения (ДД.ММ.ГГГГ)")
    chairperson: str = Field("Министр образования Свердловской области", description="Председатель")
    secretary: str = Field(..., description="Секретарь совещания")
    attendees: List[str] = Field(default_factory=list, description="Список присутствующих")


class ProtocolDraft(BaseModel):
    session_id: str = Field(..., description="Идентификатор рабочей сессии")
    metadata: ProtocolMetadata
    agenda_items: List[AgendaItem] = Field(default_factory=list)
    analytics: AnalyticsReport = Field(default_factory=AnalyticsReport)
    revision_cycle: RevisionCycleState = Field(default_factory=RevisionCycleState)
