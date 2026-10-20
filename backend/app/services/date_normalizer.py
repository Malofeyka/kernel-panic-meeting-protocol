"""Детерминированная нормализация сроков исполнения относительно даты совещания.

LLM возвращает срок дословно, как он прозвучал («до пятнадцатого ноября»,
«к следующей среде», «в двухнедельный срок»), а календарная дата вычисляется
здесь правилами. Так исключаются выдуманные моделью даты (EXT-02, EXT-05).
"""

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from backend.app.core.text import normalize_text


class DueDateKind(str, Enum):
    EXACT = "exact"
    RELATIVE = "relative"
    RECURRING = "recurring"
    VAGUE = "vague"
    UNRECOGNIZED = "unrecognized"


@dataclass(frozen=True)
class DueDate:
    kind: DueDateKind
    value: date | None = None

    @property
    def is_resolved(self) -> bool:
        return self.value is not None


_MONTH = (
    r"(январ\w*|феврал\w*|март\w*|апрел\w*|ма[йяе]|июн\w*|июл\w*|август\w*"
    r"|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)"
)
_MONTH_PREFIXES = (
    ("янв", 1), ("фев", 2), ("мар", 3), ("апр", 4), ("май", 5), ("мая", 5), ("мае", 5),
    ("июн", 6), ("июл", 7), ("авг", 8), ("сен", 9), ("окт", 10), ("ноя", 11), ("дек", 12),
)  # fmt: skip
_DAY_SUFFIX = r"(?:-?(?:го|е|ое|му|ого))?"

_ORDINAL_STEMS = {
    "перв": 1, "втор": 2, "трет": 3, "четверт": 4, "пят": 5, "шест": 6, "седьм": 7,
    "восьм": 8, "девят": 9, "десят": 10, "одиннадцат": 11, "двенадцат": 12,
    "тринадцат": 13, "четырнадцат": 14, "пятнадцат": 15, "шестнадцат": 16,
    "семнадцат": 17, "восемнадцат": 18, "девятнадцат": 19, "двадцат": 20, "тридцат": 30,
}  # fmt: skip
_ORDINAL_RE = re.compile(
    r"\b(?:(двадцать|тридцать)\s+)?("
    + "|".join(sorted(_ORDINAL_STEMS, key=len, reverse=True))
    + r")(?:ого|ое|ье|ьего|ому|ему|ьему|ья|ый|ий|ой|ым|ьим|ом|ем)\b"
)
_COUNT_WORDS = {
    "один": 1, "одного": 1, "одну": 1, "одной": 1, "два": 2, "две": 2, "двух": 2, "три": 3,
    "трех": 3, "четыре": 4, "четырех": 4, "пять": 5, "пяти": 5, "шесть": 6, "шести": 6,
    "семь": 7, "семи": 7, "восемь": 8, "восьми": 8, "девять": 9, "девяти": 9, "десять": 10,
    "десяти": 10, "четырнадцать": 14, "четырнадцати": 14, "пятнадцать": 15,
    "пятнадцати": 15, "двадцать": 20, "двадцати": 20, "тридцать": 30, "тридцати": 30,
}  # fmt: skip
_COMPOUND_PREFIXES = {
    "": 1, "одно": 1, "двух": 2, "трех": 3, "четырех": 4, "пяти": 5, "семи": 7,
    "десяти": 10, "четырнадцати": 14, "пятнадцати": 15, "тридцати": 30,
}  # fmt: skip
_WEEKDAYS = {
    "понедельник": 0, "вторник": 1, "сред": 2, "четверг": 3, "пятниц": 4, "суббот": 5,
    "воскресень": 6,
}  # fmt: skip
_ROMAN_QUARTERS = {"i": 1, "ii": 2, "iii": 3, "iv": 4}

_RECURRING_RE = re.compile(
    r"\b(ежедневн\w*|еженедельн\w*|ежемесячн\w*|ежекварталь\w*|ежегодн\w*|постоянн\w*"
    r"|регулярн\w*|систематическ\w*)"
)
_VAGUE_RE = re.compile(
    r"(в ближайшее время|оперативно|как можно скорее|срочно|незамедлительно"
    r"|в кратчайшие сроки|своевременно|в установленн\w+ срок\w*|по мере необходимости"
    r"|по готовности|в рабочем порядке|в сжатые сроки)"
)
_FULL_NUMERIC_RE = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4}|\d{2})\b")
_DAY_MONTH_RE = re.compile(rf"«?\b(\d{{1,2}}){_DAY_SUFFIX}»?\s+{_MONTH}\b(?:\s+(\d{{4}}))?")
_SHORT_NUMERIC_RE = re.compile(
    r"(?:^|\b(?:до|к|по|не позднее|срок\w*)\s*:?\s*)(\d{1,2})\.(\d{1,2})\b(?![./]\d)"
)
_DAY_OF_MONTH_RE = re.compile(rf"\b(\d{{1,2}}){_DAY_SUFFIX}\s+числ\w*")
_END_OF_PERIOD_RE = re.compile(
    r"\b(?:конц|окончани)\w*\s+(?:(следующ|текущ|этого|этой|сего|нынешн|[1-4])\w*\s+)?"
    r"(учебного года|недел|месяц|квартал|полугоди|года|год)\w*"
)
_END_OF_MONTH_RE = re.compile(rf"\b(?:конц|окончани)\w*\s+{_MONTH}\b(?:\s+(\d{{4}}))?")
_START_OF_SCHOOL_YEAR_RE = re.compile(r"\bначал\w*\s+(?:нового\s+)?учебного года")
_START_OF_MONTH_RE = re.compile(rf"\bначал\w*\s+{_MONTH}\b(?:\s+(\d{{4}}))?")
_PERIOD_RE = re.compile(
    r"\b(?:в течение|в течении|через|не позднее чем через)\s+(?:(\d+|[а-я]+)\s+)?"
    r"(рабоч\w+\s+дн|дн|день|недел|месяц)\w*"
)
_COMPOUND_PERIOD_RE = re.compile(r"\bв\s+([а-я]*?)(дневн|недельн|месячн)\w*\s+срок")
_WEEKDAY_RE = re.compile(
    r"\b(?:к|ко|до|в|во|на)\s+(следующ\w+\s+)?"
    r"(понедельник|вторник|сред|четверг|пятниц|суббот|воскресень)\w*"
)
_QUARTER_RE = re.compile(r"\b(\d|iv|iii|ii|i)\s*(?:-?(?:й|го|м|ом))?\s+квартал\w*(?:\s+(\d{4}))?")
_MONTH_ONLY_RE = re.compile(rf"\b(в|во|до|к|ко)\s+{_MONTH}\b(?:\s+(\d{{4}}))?")


def _month_number(word: str) -> int:
    for prefix, number in _MONTH_PREFIXES:
        if word.startswith(prefix):
            return number
    raise ValueError(f"Неизвестный месяц: {word}")


def replace_ordinals(text: str) -> str:
    """«пятнадцатого» -> «15», «двадцать пятому» -> «25»."""

    def replace(match: re.Match[str]) -> str:
        tens = {"двадцать": 20, "тридцать": 30}.get(match.group(1) or "", 0)
        return str(tens + _ORDINAL_STEMS[match.group(2)])

    return _ORDINAL_RE.sub(replace, text)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _resolve_day_month(day: int, month: int, year: int | None, ref: date) -> date | None:
    if year is not None:
        return _safe_date(year, month, day)
    candidate = _safe_date(ref.year, month, day)
    if candidate is None:
        return None
    if candidate < ref - timedelta(days=45):
        return _safe_date(ref.year + 1, month, day)
    return candidate


def _last_day_of_month(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _add_business_days(value: date, days: int) -> date:
    current = value
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def _parse_count(raw: str | None) -> int | None:
    if raw is None:
        return 1
    if raw.isdigit():
        return int(raw)
    return _COUNT_WORDS.get(raw)


def _end_of_period(period: str, modifier: str | None, ref: date) -> date:
    is_next = modifier == "следующ"
    numbered = modifier is not None and modifier.isdigit()
    if numbered and period.startswith(("квартал", "полугоди")):
        number = int(modifier or "1")
        end_month = number * 3 if period.startswith("квартал") else min(number, 2) * 6
        end = _last_day_of_month(ref.year, end_month)
        return end if end >= ref else _last_day_of_month(ref.year + 1, end_month)
    if period.startswith("недел"):
        friday = ref - timedelta(days=ref.weekday()) + timedelta(days=4)
        if friday < ref:
            friday += timedelta(days=7)
        return friday + timedelta(days=7 if is_next else 0)
    if period.startswith("месяц"):
        base = _add_months(ref.replace(day=1), 1 if is_next else 0)
        return _last_day_of_month(base.year, base.month)
    if period.startswith("квартал"):
        quarter = (ref.month - 1) // 3 + (1 if is_next else 0)
        year = ref.year + quarter // 4
        end_month = (quarter % 4) * 3 + 3
        return _last_day_of_month(year, end_month)
    if period.startswith("полугоди"):
        if ref.month <= 6:
            return date(ref.year, 12, 31) if is_next else date(ref.year, 6, 30)
        return date(ref.year + 1, 6, 30) if is_next else date(ref.year, 12, 31)
    if period == "учебного года":
        end = date(ref.year, 8, 31)
        return end if end >= ref else date(ref.year + 1, 8, 31)
    return date(ref.year + (1 if is_next else 0), 12, 31)


def normalize_due_date(phrase: str | None, meeting_date: date) -> DueDate:
    """Переводит прозвучавший срок в календарную дату относительно даты совещания."""
    if phrase is None:
        return DueDate(DueDateKind.UNRECOGNIZED)
    text = replace_ordinals(normalize_text(phrase))
    if not text:
        return DueDate(DueDateKind.UNRECOGNIZED)
    ref = meeting_date

    if _RECURRING_RE.search(text):
        return DueDate(DueDateKind.RECURRING)

    if match := _FULL_NUMERIC_RE.search(text):
        day, month, raw_year = int(match.group(1)), int(match.group(2)), match.group(3)
        full_year = int(raw_year) + (2000 if len(raw_year) == 2 else 0)
        return _exact(_safe_date(full_year, month, day))

    if match := _DAY_MONTH_RE.search(text):
        year = int(match.group(3)) if match.group(3) else None
        return _exact(
            _resolve_day_month(int(match.group(1)), _month_number(match.group(2)), year, ref)
        )

    if match := _SHORT_NUMERIC_RE.search(text):
        return _exact(_resolve_day_month(int(match.group(1)), int(match.group(2)), None, ref))

    if match := _DAY_OF_MONTH_RE.search(text):
        day = int(match.group(1))
        base = ref if day >= ref.day else _add_months(ref.replace(day=1), 1)
        return _relative(_safe_date(base.year, base.month, day))

    if match := _END_OF_MONTH_RE.search(text):
        month = _month_number(match.group(1))
        year = int(match.group(2)) if match.group(2) else None
        last = _last_day_of_month(year or ref.year, month)
        if year is None and last < ref:
            last = _last_day_of_month(ref.year + 1, month)
        return _relative(last)

    if match := _END_OF_PERIOD_RE.search(text):
        return _relative(_end_of_period(match.group(2), match.group(1), ref))

    if _START_OF_SCHOOL_YEAR_RE.search(text):
        start = date(ref.year, 9, 1)
        return _relative(start if start >= ref else date(ref.year + 1, 9, 1))

    if match := _START_OF_MONTH_RE.search(text):
        year = int(match.group(2)) if match.group(2) else None
        return _relative(_resolve_day_month(1, _month_number(match.group(1)), year, ref))

    if match := _PERIOD_RE.search(text):
        count = _parse_count(match.group(1))
        if count is not None:
            unit = match.group(2)
            if unit.startswith("рабоч"):
                return _relative(_add_business_days(ref, count))
            if unit.startswith(("дн", "день")):
                return _relative(ref + timedelta(days=count))
            if unit.startswith("недел"):
                return _relative(ref + timedelta(weeks=count))
            return _relative(_add_months(ref, count))

    if match := _COMPOUND_PERIOD_RE.search(text):
        count = _COMPOUND_PREFIXES.get(match.group(1))
        if count is not None:
            unit = match.group(2)
            if unit == "дневн":
                return _relative(ref + timedelta(days=count))
            if unit == "недельн":
                return _relative(ref + timedelta(weeks=count))
            return _relative(_add_months(ref, count))

    if re.search(r"\bпослезавтра\b", text):
        return _relative(ref + timedelta(days=2))
    if re.search(r"\bзавтра\b", text):
        return _relative(ref + timedelta(days=1))
    if re.search(r"\bсегодня\b|\bконца дня\b", text):
        return _relative(ref)

    if match := _WEEKDAY_RE.search(text):
        target = _WEEKDAYS[match.group(2)]
        if match.group(1):
            next_monday = ref - timedelta(days=ref.weekday()) + timedelta(days=7)
            return _relative(next_monday + timedelta(days=target))
        days_ahead = (target - ref.weekday()) % 7 or 7
        return _relative(ref + timedelta(days=days_ahead))

    if match := _QUARTER_RE.search(text):
        raw_quarter = match.group(1)
        quarter = int(raw_quarter) if raw_quarter.isdigit() else _ROMAN_QUARTERS[raw_quarter]
        if 1 <= quarter <= 4:
            year = int(match.group(2)) if match.group(2) else ref.year
            end = _last_day_of_month(year, quarter * 3)
            if match.group(2) is None and end < ref:
                end = _last_day_of_month(ref.year + 1, quarter * 3)
            return _relative(end)

    if match := _MONTH_ONLY_RE.search(text):
        month = _month_number(match.group(2))
        year = int(match.group(3)) if match.group(3) else None
        if match.group(1) in {"в", "во"}:
            end = _last_day_of_month(year or ref.year, month)
            if year is None and end < ref:
                end = _last_day_of_month(ref.year + 1, month)
            return _relative(end)
        first = _resolve_day_month(1, month, year, ref)
        if first is not None and year is None and first <= ref:
            first = date(ref.year + 1, month, 1)
        return _relative(first - timedelta(days=1) if first else None)

    if _VAGUE_RE.search(text):
        return DueDate(DueDateKind.VAGUE)
    return DueDate(DueDateKind.UNRECOGNIZED)


def _exact(value: date | None) -> DueDate:
    return DueDate(DueDateKind.EXACT, value) if value else DueDate(DueDateKind.UNRECOGNIZED)


def _relative(value: date | None) -> DueDate:
    return DueDate(DueDateKind.RELATIVE, value) if value else DueDate(DueDateKind.UNRECOGNIZED)


def find_absolute_date(text: str) -> date | None:
    """Первая дата с явно указанным годом (для шапок архивных протоколов)."""
    normalized = normalize_text(text)
    candidates: list[tuple[int, date]] = []
    if match := _FULL_NUMERIC_RE.search(normalized):
        raw_year = match.group(3)
        year = int(raw_year) + (2000 if len(raw_year) == 2 else 0)
        parsed = _safe_date(year, int(match.group(2)), int(match.group(1)))
        if parsed:
            candidates.append((match.start(), parsed))
    for match in _DAY_MONTH_RE.finditer(normalized):
        if match.group(3):
            parsed = _safe_date(
                int(match.group(3)), _month_number(match.group(2)), int(match.group(1))
            )
            if parsed:
                candidates.append((match.start(), parsed))
            break
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def dates_mentioned(text: str, meeting_date: date, window: int = 8) -> set[date]:
    """Все даты, которые можно получить из фрагментов текста (для сверки срока с цитатой)."""
    words = normalize_text(text).split()
    found: set[date] = set()
    step = max(1, window // 2)
    for start in range(0, max(1, len(words)), step):
        due = normalize_due_date(" ".join(words[start : start + window]), meeting_date)
        if due.value is not None:
            found.add(due.value)
    return found
