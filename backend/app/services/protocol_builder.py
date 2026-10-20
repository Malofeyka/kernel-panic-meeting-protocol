"""Сборка проекта протокола из сырого результата LLM с проверкой фактов.

Для каждого решения/поручения:
1. цитата ищется в стенограмме (иначе пункт отклоняется как неподтверждённый);
2. исполнитель и срок принимаются, только если они действительно звучат в цитате;
3. исполнитель сопоставляется со списком участников, срок переводится в дату;
4. пункт привязывается к вопросу повестки (или к разделу «Разное»).
"""

from dataclasses import dataclass, field
from datetime import date

from backend.app.core.config import Settings
from backend.app.core.text import normalize_text, similarity
from backend.app.schemas.documents import MeetingContext
from backend.app.schemas.protocol import (
    ActionItem,
    AgendaItem,
    Decision,
    GapIssue,
    GapType,
    ItemOrigin,
    Severity,
    format_ru_date,
)
from backend.app.services.attendee_matcher import AttendeeMatcher
from backend.app.services.date_normalizer import (
    DueDateKind,
    dates_mentioned,
    normalize_due_date,
    replace_ordinals,
)
from backend.app.services.extraction import ExtractionResult, RawActionItem, RawDecision
from backend.app.services.transcript import GroundingResult, TranscriptIndex, format_timecode

MISC_TOPIC = "Разное"
DEFAULT_TOPIC = "Общие вопросы"


@dataclass
class BuildResult:
    agenda_items: list[AgendaItem]
    notes: list[GapIssue] = field(default_factory=list)


def _shorten(text: str, limit: int = 160) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class ProtocolBuilder:
    def __init__(
        self,
        index: TranscriptIndex,
        matcher: AttendeeMatcher,
        meeting_date: date,
        settings: Settings,
    ) -> None:
        self._index = index
        self._matcher = matcher
        self._meeting_date = meeting_date
        self._settings = settings

    # --- переиспользуется контроллером правок ---
    def make_action_item(
        self,
        task: str,
        assignee_mention: str | None,
        due_date_mention: str | None,
        quote: str | None,
        grounding: GroundingResult | None,
        evidence_text: str,
        origin: ItemOrigin = ItemOrigin.AI,
        item_id: str | None = None,
    ) -> ActionItem:
        resolution = self._matcher.resolve(assignee_mention)
        if assignee_mention and not self.assignee_supported(
            assignee_mention, resolution.assignee if resolution.matched else None, evidence_text
        ):
            assignee_mention = None
            resolution = self._matcher.resolve(None)

        due = normalize_due_date(due_date_mention, self._meeting_date)
        if due_date_mention and not self.due_supported(due_date_mention, due.value, evidence_text):
            due_date_mention = None
            due = normalize_due_date(None, self._meeting_date)
        values: dict[str, object] = {
            "task": task.strip(),
            "assignee": resolution.assignee,
            "assignee_role": resolution.role,
            "assignee_raw": assignee_mention,
            "due_date": format_ru_date(due.value) if due.value else None,
            "due_date_raw": due_date_mention,
            "is_recurring": due.kind == DueDateKind.RECURRING,
            "quote": quote,
            "source_start": grounding.start if grounding and grounding.grounded else None,
            "source_end": grounding.end if grounding and grounding.grounded else None,
            "origin": origin,
        }
        if item_id:
            values["id"] = item_id
        return ActionItem.model_validate(values)

    def assignee_supported(self, mention: str, matched: str | None, evidence: str) -> bool:
        if self._index.mention_supported(mention, evidence):
            return True
        return matched is not None and self._matcher.mentioned_in(matched, evidence)

    def due_supported(self, mention: str, value: date | None, evidence: str) -> bool:
        if self._index.mention_supported(
            replace_ordinals(normalize_text(mention)), replace_ordinals(normalize_text(evidence))
        ):
            return True
        return value is not None and value in dates_mentioned(evidence, self._meeting_date)

    def resolve_reporter(self, mention: str | None) -> str | None:
        if not mention or not self._index.contains(mention):
            return None
        resolution = self._matcher.resolve(mention)
        return resolution.assignee

    # --- основной сценарий ---
    def build(self, extraction: ExtractionResult, context: MeetingContext) -> BuildResult:
        sections: dict[int, AgendaItem] = {
            topic.number: AgendaItem(
                item_number=topic.number, topic=topic.title, reporter=topic.reporter
            )
            for topic in context.agenda
        }
        notes: list[GapIssue] = []

        def section_for(agenda_item: int | None, topic: str | None) -> AgendaItem:
            if context.agenda:
                if agenda_item is not None and 1 <= agenda_item <= len(context.agenda):
                    return sections[agenda_item]
                if topic:
                    best = max(
                        context.agenda, key=lambda candidate: similarity(topic, candidate.title)
                    )
                    if similarity(topic, best.title) >= 0.35:
                        return sections[best.number]
                return _misc_section()
            title = topic or DEFAULT_TOPIC
            for section in sections.values():
                if similarity(title, section.topic) >= 0.5:
                    return section
            number = len(sections) + 1
            sections[number] = AgendaItem(item_number=number, topic=title)
            return sections[number]

        def _misc_section() -> AgendaItem:
            for section in sections.values():
                if section.topic == MISC_TOPIC and section.item_number > len(context.agenda):
                    return section
            number = len(sections) + 1
            sections[number] = AgendaItem(item_number=number, topic=MISC_TOPIC)
            return sections[number]

        for decision in extraction.decisions:
            built = self._build_decision(decision, notes)
            if built:
                section_for(decision.agenda_item, decision.topic).decisions.append(built)

        for raw in extraction.action_items:
            action = self._build_action(raw, notes)
            if action:
                section_for(raw.agenda_item, raw.topic).action_items.append(action)

        for report in extraction.reports:
            if report.agenda_item in sections:
                section = sections[report.agenda_item]
                if section.reporter is None:
                    section.reporter = self.resolve_reporter(report.reporter_mention)

        for chunk in extraction.failed_chunks:
            first = self._index.segments[chunk.first_segment]
            last = self._index.segments[chunk.last_segment]
            notes.append(
                GapIssue(
                    type=GapType.UNPROCESSED_FRAGMENT,
                    severity=Severity.HIGH,
                    description=(
                        f"Фрагмент стенограммы {format_timecode(first.start)}–"
                        f"{format_timecode(last.end)} не удалось обработать моделью. "
                        "Проверьте его вручную: решения из него могли не попасть в проект."
                    ),
                    source_start=first.start,
                )
            )

        ordered = [sections[number] for number in sorted(sections)]
        return BuildResult(agenda_items=ordered, notes=notes)

    def _reject(self, kind: str, text: str, quote: str | None, notes: list[GapIssue]) -> None:
        notes.append(
            GapIssue(
                type=GapType.REJECTED_UNGROUNDED,
                severity=Severity.MEDIUM,
                description=(
                    f"{kind} «{_shorten(text)}» исключено из проекта: подтверждающая цитата "
                    "не найдена в стенограмме. При необходимости добавьте вручную."
                ),
                context_quote=quote,
            )
        )

    def _build_decision(self, raw: RawDecision, notes: list[GapIssue]) -> Decision | None:
        grounding = self._index.locate(raw.quote, raw.segment_ids)
        if not grounding.grounded and self._settings.drop_ungrounded_items:
            self._reject("Решение", raw.text, raw.quote, notes)
            return None
        return Decision(
            text=raw.text.strip(),
            quote=raw.quote,
            source_start=grounding.start,
            source_end=grounding.end,
        )

    def _build_action(self, raw: RawActionItem, notes: list[GapIssue]) -> ActionItem | None:
        grounding = self._index.locate(raw.quote, raw.segment_ids)
        if not grounding.grounded and self._settings.drop_ungrounded_items:
            self._reject("Поручение", raw.task, raw.quote, notes)
            return None
        # Исполнитель и срок сверяются только с подтверждённым текстом стенограммы:
        # неподтверждённая цитата модели доказательством не является.
        evidence = (
            f"{raw.quote or ''} {grounding.window_text(self._index)}" if grounding.grounded else ""
        )
        return self.make_action_item(
            task=raw.task,
            assignee_mention=raw.assignee_mention,
            due_date_mention=raw.due_date_mention,
            quote=raw.quote,
            grounding=grounding,
            evidence_text=evidence,
        )
