"""Аналитика проекта протокола (BE-202, BE-301).

Отдельный от протокола отчёт, каждый элемент которого ссылается на конкретные
пункты (`action_item_ids`, номер вопроса) и цитаты:
- пробелы: нет срока / размытый срок / нет исполнителя / неоднозначный исполнитель /
  исполнитель не из списка / вопрос повестки без решения;
- противоречия внутри встречи (одно поручение — разные сроки или исполнители);
- противоречия и повторы относительно архивных протоколов;
- риски: срок в прошлом, слишком короткий срок, срок на выходной, перегрузка исполнителя.

Анализ полностью детерминированный — аналитика не может «придумать» замечание.
"""

from collections import defaultdict
from datetime import date

from backend.app.core.config import Settings
from backend.app.core.text import similarity
from backend.app.schemas.documents import ArchiveProtocol
from backend.app.schemas.protocol import (
    ActionItem,
    AnalyticsReport,
    Contradiction,
    ContradictionScope,
    GapIssue,
    GapType,
    ProtocolDraft,
    Risk,
    RiskType,
    Severity,
    parse_ru_date,
)
from backend.app.services.attendee_matcher import AttendeeMatcher, same_person
from backend.app.services.date_normalizer import DueDateKind, normalize_due_date

SAME_TASK_THRESHOLD = 0.6
ARCHIVE_MATCH_THRESHOLD = 0.5
DUPLICATE_THRESHOLD = 0.85
TIGHT_DEADLINE_DAYS = 2


def _short(text: str, limit: int = 120) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _due(action: ActionItem) -> date | None:
    return parse_ru_date(action.due_date) if action.due_date else None


def _action_gap(
    gap_type: GapType, severity: Severity, description: str, agenda_number: int, action: ActionItem
) -> GapIssue:
    return GapIssue(
        type=gap_type,
        severity=severity,
        description=description,
        agenda_item_number=agenda_number,
        action_item_id=action.id,
        context_quote=action.quote,
        source_start=action.source_start,
    )


class AnalyticsEngine:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def analyze(
        self,
        draft: ProtocolDraft,
        archive: list[ArchiveProtocol],
        matcher: AttendeeMatcher,
        pipeline_notes: list[GapIssue] | None = None,
        input_warnings: list[str] | None = None,
    ) -> AnalyticsReport:
        meeting_date = parse_ru_date(draft.metadata.meeting_date)
        report = AnalyticsReport()
        report.gaps.extend(self._input_gaps(matcher, input_warnings or []))
        report.gaps.extend(self._item_gaps(draft, matcher, meeting_date))
        report.gaps.extend(pipeline_notes or [])
        report.contradictions.extend(self._meeting_contradictions(draft))
        archive_contradictions, archive_risks = self._archive_checks(draft, archive, meeting_date)
        report.contradictions.extend(archive_contradictions)
        report.risks.extend(self._deadline_risks(draft, meeting_date))
        report.risks.extend(self._overload_risks(draft))
        report.risks.extend(archive_risks)
        report.risks.extend(self._duplicate_risks(draft))
        return report

    @staticmethod
    def _input_gaps(matcher: AttendeeMatcher, warnings: list[str]) -> list[GapIssue]:
        gaps = [
            GapIssue(type=GapType.MISSING_INPUT, severity=Severity.LOW, description=warning)
            for warning in warnings
        ]
        if not matcher.has_attendees:
            gaps.append(
                GapIssue(
                    type=GapType.MISSING_INPUT,
                    severity=Severity.LOW,
                    description=(
                        "Список участников не загружен: ответственные не сверены со штатным "
                        "списком, должности не подставлены."
                    ),
                )
            )
        return gaps

    def _item_gaps(
        self, draft: ProtocolDraft, matcher: AttendeeMatcher, meeting_date: date
    ) -> list[GapIssue]:
        gaps: list[GapIssue] = []
        for agenda_item in draft.agenda_items:
            if not agenda_item.decisions and not agenda_item.action_items:
                gaps.append(
                    GapIssue(
                        type=GapType.NO_DECISION_FOR_AGENDA_ITEM,
                        severity=Severity.MEDIUM,
                        description=(
                            f"По вопросу {agenda_item.item_number} «{_short(agenda_item.topic)}» "
                            "в стенограмме не зафиксировано ни решения, ни поручения."
                        ),
                        agenda_item_number=agenda_item.item_number,
                    )
                )
        for agenda_item, index, action in draft.iter_action_items():
            label = f"п. {agenda_item.item_number}.{index}"
            number = agenda_item.item_number
            if action.due_date is None and not action.is_recurring:
                due = normalize_due_date(action.due_date_raw, meeting_date)
                if action.due_date_raw and due.kind == DueDateKind.VAGUE:
                    gaps.append(
                        _action_gap(
                            GapType.VAGUE_DUE_DATE,
                            Severity.MEDIUM,
                            f"{label}: срок «{action.due_date_raw}» не позволяет контролировать "
                            f"исполнение — укажите дату (поручение: «{_short(action.task)}»).",
                            number,
                            action,
                        )
                    )
                else:
                    heard = f" (прозвучало: «{action.due_date_raw}»)" if action.due_date_raw else ""
                    gaps.append(
                        _action_gap(
                            GapType.MISSING_DUE_DATE,
                            Severity.HIGH,
                            f"{label}: поручение «{_short(action.task)}» не содержит срока "
                            f"исполнения{heard}.",
                            number,
                            action,
                        )
                    )
            if action.assignee is None:
                resolution = matcher.resolve(action.assignee_raw)
                if resolution.ambiguous:
                    gaps.append(
                        _action_gap(
                            GapType.AMBIGUOUS_ASSIGNEE,
                            Severity.HIGH,
                            f"{label}: исполнитель «{action.assignee_raw}» неоднозначен — "
                            f"подходят: {', '.join(resolution.candidates)}.",
                            number,
                            action,
                        )
                    )
                else:
                    gaps.append(
                        _action_gap(
                            GapType.MISSING_ASSIGNEE,
                            Severity.HIGH,
                            f"{label}: для поручения «{_short(action.task)}» не назван "
                            "ответственный исполнитель.",
                            number,
                            action,
                        )
                    )
            elif matcher.has_attendees and action.assignee not in matcher.short_names:
                gaps.append(
                    _action_gap(
                        GapType.UNMATCHED_ASSIGNEE,
                        Severity.LOW,
                        f"{label}: исполнитель «{action.assignee}» отсутствует в списке "
                        "участников — проверьте написание или уточните ответственного.",
                        number,
                        action,
                    )
                )
        return gaps

    @staticmethod
    def _meeting_contradictions(draft: ProtocolDraft) -> list[Contradiction]:
        items = draft.iter_action_items()
        result: list[Contradiction] = []
        for i, (_, _, left) in enumerate(items):
            for _, _, right in items[i + 1 :]:
                if similarity(left.task, right.task) < SAME_TASK_THRESHOLD:
                    continue
                left_label = draft.action_item_label(left.id)
                right_label = draft.action_item_label(right.id)
                problems: list[str] = []
                if left.assignee and right.assignee and left.assignee != right.assignee:
                    problems.append(f"разные исполнители ({left.assignee} / {right.assignee})")
                if left.due_date and right.due_date and left.due_date != right.due_date:
                    problems.append(f"разные сроки ({left.due_date} / {right.due_date})")
                if not problems:
                    continue
                result.append(
                    Contradiction(
                        scope=ContradictionScope.MEETING,
                        description=(
                            f"{left_label} и {right_label} описывают одно поручение, "
                            f"но указаны {' и '.join(problems)}."
                        ),
                        action_item_ids=[left.id, right.id],
                        quotes=[quote for quote in (left.quote, right.quote) if quote],
                    )
                )
        return result

    @staticmethod
    def _duplicate_risks(draft: ProtocolDraft) -> list[Risk]:
        items = draft.iter_action_items()
        risks: list[Risk] = []
        for i, (_, _, left) in enumerate(items):
            for _, _, right in items[i + 1 :]:
                if (
                    similarity(left.task, right.task) >= DUPLICATE_THRESHOLD
                    and left.assignee == right.assignee
                    and left.due_date == right.due_date
                ):
                    risks.append(
                        Risk(
                            type=RiskType.DUPLICATE_ITEM,
                            severity=Severity.LOW,
                            description=(
                                f"{draft.action_item_label(left.id)} и "
                                f"{draft.action_item_label(right.id)} дублируют друг друга — "
                                "оставьте один пункт."
                            ),
                            action_item_ids=[left.id, right.id],
                        )
                    )
        return risks

    def _archive_checks(
        self, draft: ProtocolDraft, archive: list[ArchiveProtocol], meeting_date: date
    ) -> tuple[list[Contradiction], list[Risk]]:
        contradictions: list[Contradiction] = []
        risks: list[Risk] = []
        for _, _, action in draft.iter_action_items():
            label = draft.action_item_label(action.id)
            for protocol in archive:
                for old in protocol.action_items:
                    if similarity(action.task, old.task) < ARCHIVE_MATCH_THRESHOLD:
                        continue
                    reference = protocol.label + (
                        f", п. {old.item_label}" if old.item_label else ""
                    )
                    old_due = parse_ru_date(old.due_date) if old.due_date else None
                    if (
                        action.assignee
                        and old.assignee
                        and not same_person(action.assignee, old.assignee)
                    ):
                        contradictions.append(
                            Contradiction(
                                scope=ContradictionScope.ARCHIVE,
                                description=(
                                    f"{label}: аналогичное поручение ранее было дано "
                                    f"{old.assignee} ({reference}), теперь — {action.assignee}. "
                                    "Уточните, кто отвечает за исполнение."
                                ),
                                action_item_ids=[action.id],
                                quotes=[q for q in (action.quote, old.task) if q],
                                archive_reference=reference,
                            )
                        )
                    elif (
                        action.due_date
                        and old_due is not None
                        and old_due >= meeting_date
                        and action.due_date != old.due_date
                    ):
                        contradictions.append(
                            Contradiction(
                                scope=ContradictionScope.ARCHIVE,
                                description=(
                                    f"{label}: срок по действующему поручению ({reference}) — "
                                    f"{old.due_date}, сейчас назван {action.due_date}. "
                                    "Зафиксируйте перенос срока явно."
                                ),
                                action_item_ids=[action.id],
                                quotes=[q for q in (action.quote, old.task) if q],
                                archive_reference=reference,
                            )
                        )
                    else:
                        overdue = old_due is not None and old_due < meeting_date
                        risks.append(
                            Risk(
                                type=RiskType.REPEATED_ASSIGNMENT,
                                severity=Severity.MEDIUM if overdue else Severity.LOW,
                                description=(
                                    f"{label}: поручение повторяет пункт из {reference}"
                                    + (
                                        f" со сроком {old.due_date} — вероятно, оно не "
                                        "исполнено в срок."
                                        if overdue
                                        else "."
                                    )
                                ),
                                action_item_ids=[action.id],
                                archive_reference=reference,
                            )
                        )
        return contradictions, risks

    @staticmethod
    def _deadline_risks(draft: ProtocolDraft, meeting_date: date) -> list[Risk]:
        risks: list[Risk] = []
        for _, _, action in draft.iter_action_items():
            due = _due(action)
            if due is None:
                continue
            label = draft.action_item_label(action.id)
            delta = (due - meeting_date).days
            if delta < 0:
                risks.append(
                    Risk(
                        type=RiskType.DEADLINE_IN_PAST,
                        severity=Severity.HIGH,
                        description=(
                            f"{label}: срок {action.due_date} раньше даты совещания "
                            f"{draft.metadata.meeting_date} — проверьте дату."
                        ),
                        action_item_ids=[action.id],
                    )
                )
            elif delta <= TIGHT_DEADLINE_DAYS:
                risks.append(
                    Risk(
                        type=RiskType.TIGHT_DEADLINE,
                        severity=Severity.MEDIUM,
                        description=(
                            f"{label}: на исполнение {delta} дн. (срок {action.due_date}) — "
                            "протокол может быть доведён до исполнителя позже срока."
                        ),
                        action_item_ids=[action.id],
                    )
                )
            if due.weekday() >= 5:
                risks.append(
                    Risk(
                        type=RiskType.WEEKEND_DEADLINE,
                        severity=Severity.LOW,
                        description=f"{label}: срок {action.due_date} приходится на выходной день.",
                        action_item_ids=[action.id],
                    )
                )
        return risks

    def _overload_risks(self, draft: ProtocolDraft) -> list[Risk]:
        by_assignee: dict[str, list[str]] = defaultdict(list)
        for _, _, action in draft.iter_action_items():
            if action.assignee:
                by_assignee[action.assignee].append(action.id)
        threshold = self._settings.assignee_overload_threshold
        return [
            Risk(
                type=RiskType.ASSIGNEE_OVERLOAD,
                severity=Severity.MEDIUM,
                description=(
                    f"На {assignee} приходится {len(ids)} поручений: "
                    f"{', '.join(draft.action_item_label(item_id) for item_id in ids)}."
                ),
                action_item_ids=ids,
            )
            for assignee, ids in by_assignee.items()
            if len(ids) >= threshold
        ]
