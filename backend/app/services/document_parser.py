"""Парсер сопутствующих материалов совещания (BE-103).

Извлекает текст из TXT/MD/DOCX/PDF и разбирает:
- повестку -> пронумерованные вопросы и докладчики;
- список участников -> ФИО, должности, председатель и секретарь;
- архивные протоколы -> номер, дата и перечень поручений для сверки.

Разбор эвристический и детерминированный (без LLM): то, что не распознано,
просто не попадает в контекст, а не домысливается.
"""

import re
from datetime import date
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from backend.app.core.text import find_person_name, normalize_text, short_name
from backend.app.schemas.documents import AgendaTopic, ArchiveActionItem, ArchiveProtocol
from backend.app.schemas.protocol import Attendee, format_ru_date
from backend.app.services.date_normalizer import (
    DueDateKind,
    find_absolute_date,
    normalize_due_date,
)

SUPPORTED_DOCUMENT_SUFFIXES = frozenset({".txt", ".md", ".docx", ".pdf"})
CELL_SEPARATOR = " | "

_BULLET_RE = re.compile(r"^\s*(?:[-•*–—]\s*|\d{1,3}[.)]\s+)")
_CHAIR_RE = re.compile(r"^\s*председател\w*\s*[:\-–—]?\s*", re.IGNORECASE)
_SECRETARY_RE = re.compile(r"^\s*секретар\w*\s*[:\-–—]?\s*", re.IGNORECASE)
_SEPARATORS_RE = re.compile(r"^[\s,;:\-–—()|]+|[\s,;:\-–—()|]+$")
_HEADER_HINTS = (
    "список участник", "список присутств", "присутствовали", "участники совещания",
    "приглашенные", "фио", "повестка",
)  # fmt: skip
_AGENDA_NUMBER_RE = re.compile(r"^\s*(\d{1,2})\s*[.)]\s*(?!\d)(.+)$")
_REPORTER_RE = re.compile(
    r"[(\s,;.]*(?:докладчик\w*|выступающ\w*|информаци\w* представляет|содокладчик\w*)"
    r"\s*[:\-–—]?\s*(.+?)\)?\s*$",
    re.IGNORECASE,
)
_PROTOCOL_NUMBER_RE = re.compile(r"№\s*([\w\-/.]+)")
_ARCHIVE_ITEM_RE = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2})*)\.?\s+(.{10,})$")
_RESPONSIBLE_RE = re.compile(
    r"(?:ответственн\w*|исполнител\w*)\s*[:\-–—]\s*([^;\n]+?)(?=\s*(?:срок|;|$))", re.IGNORECASE
)
_DUE_PHRASE_RE = re.compile(r"срок\w*\s*(?:исполнения)?\s*[:\-–—]?\s*([^;\n]+)", re.IGNORECASE)
_TASK_VERBS = (
    "обеспеч", "подготов", "представ", "направ", "провест", "организ", "разработ",
    "рассмотр", "приня", "проработ", "внест", "утверд", "довест", "осуществ", "усил",
    "продолж", "согласов", "информир", "проанализ", "актуализ", "завершит", "сформир",
    "поручит", "поручено", "взять на контроль", "провер", "доложит", "уведом",
)  # fmt: skip


class DocumentParseError(ValueError):
    pass


def _paragraph_and_table_lines(path: Path) -> list[str]:
    document = Document(str(path))
    lines: list[str] = []
    for block in document.iter_inner_content():
        if isinstance(block, Paragraph):
            lines.append(block.text)
        elif isinstance(block, Table):
            for row in block.rows:
                cells: list[str] = []
                for cell in row.cells:
                    text = " ".join(cell.text.split())
                    if not cells or cells[-1] != text:  # объединённые ячейки повторяются
                        cells.append(text)
                if any(cells):
                    lines.append(CELL_SEPARATOR.join(cells))
    return lines


def _read_plain_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentParseError(f"Не удалось определить кодировку файла {path.name}")


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_text(path: Path) -> str:
    suffix = path.suffix.casefold()
    try:
        if suffix in {".txt", ".md"}:
            return _read_plain_text(path)
        if suffix == ".docx":
            return "\n".join(_paragraph_and_table_lines(path))
        if suffix == ".pdf":
            return _read_pdf(path)
    except DocumentParseError:
        raise
    except Exception as exc:
        raise DocumentParseError(f"Не удалось прочитать файл {path.name}: {exc}") from exc
    raise DocumentParseError(
        f"Формат {suffix or 'без расширения'} не поддерживается: используйте TXT, DOCX или PDF"
    )


def _clean(text: str) -> str:
    return _SEPARATORS_RE.sub("", " ".join(text.split()))


def _is_header(line: str) -> bool:
    normalized = normalize_text(line)
    return any(normalized.startswith(hint) for hint in _HEADER_HINTS) and len(normalized) < 60


def parse_attendees(text: str) -> tuple[list[Attendee], str | None, str | None]:
    """Возвращает (участники, председатель, секретарь) в форме «Фамилия И.О.»."""
    attendees: list[Attendee] = []
    seen: set[str] = set()
    chairperson: str | None = None
    secretary: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or _is_header(line):
            continue
        role: str | None = None
        if _CHAIR_RE.match(line):
            role, line = "chair", _CHAIR_RE.sub("", line, count=1)
        elif _SECRETARY_RE.match(line):
            role, line = "secretary", _SECRETARY_RE.sub("", line, count=1)
        line = _BULLET_RE.sub("", line, count=1)

        cells = [cell for cell in line.split(CELL_SEPARATOR.strip()) if cell.strip()]
        name_match = None
        position_parts: list[str] = []
        for cell in cells:
            found = find_person_name(cell) if name_match is None else None
            if found:
                name_match = found
                rest = _clean(cell[: found[1]] + " " + cell[found[2] :])
                if rest:
                    position_parts.append(rest)
            elif not re.fullmatch(r"\s*\d+[.)]?\s*", cell):
                position_parts.append(_clean(cell))
        if name_match is None:
            continue

        full_name = name_match[0]
        key = normalize_text(short_name(full_name))
        position = _clean(", ".join(part for part in position_parts if part)) or None
        if key not in seen:
            seen.add(key)
            attendees.append(Attendee(full_name=full_name, position=position))
        if role == "chair":
            chairperson = short_name(full_name)
        elif role == "secretary":
            secretary = short_name(full_name)
    return attendees, chairperson, secretary


def _split_reporter(text: str) -> tuple[str, str | None]:
    match = _REPORTER_RE.search(text)
    if not match:
        return _clean(text), None
    topic = _clean(text[: match.start()])
    reporter_text = _clean(match.group(1))
    person = find_person_name(reporter_text)
    reporter = short_name(person[0]) if person else reporter_text or None
    return topic, reporter


def parse_agenda(text: str) -> list[AgendaTopic]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    numbered: list[tuple[int, str]] = []
    reporters: dict[int, str] = {}
    for line in lines:
        if _is_header(line):
            continue
        match = _AGENDA_NUMBER_RE.match(line)
        if match:
            numbered.append((int(match.group(1)), match.group(2)))
            continue
        if not numbered:
            continue
        reporter_match = _REPORTER_RE.match(line)
        if reporter_match and normalize_text(line).startswith(("докладчик", "выступ", "содоклад")):
            _, reporter = _split_reporter(line)
            if reporter:
                reporters[len(numbered) - 1] = reporter
        else:  # перенос длинной темы на следующую строку
            number, title = numbered[-1]
            numbered[-1] = (number, f"{title} {line}")

    if not numbered:  # повестка без нумерации: каждая строка — отдельный вопрос
        numbered = [
            (index, line)
            for index, line in enumerate((ln for ln in lines if not _is_header(ln)), start=1)
        ]

    topics: list[AgendaTopic] = []
    for position, (_, raw_title) in enumerate(numbered):
        title, reporter = _split_reporter(raw_title)
        if not title:
            continue
        topics.append(
            AgendaTopic(
                number=len(topics) + 1,
                title=title,
                reporter=reporters.get(position) or reporter,
            )
        )
    return topics


def _looks_like_task(text: str) -> bool:
    normalized = normalize_text(text)
    return any(verb in normalized for verb in _TASK_VERBS) or "срок" in normalized


def _due_from_text(text: str, reference_year_date: str | None) -> tuple[str | None, bool]:
    ref = date.today()
    if reference_year_date:
        parsed = find_absolute_date(reference_year_date)
        if parsed:
            ref = parsed
    phrase_match = _DUE_PHRASE_RE.search(text)
    candidates = [phrase_match.group(1)] if phrase_match else []
    candidates.append(text)
    for candidate in candidates:
        due = normalize_due_date(candidate, ref)
        if due.kind == DueDateKind.RECURRING:
            return None, True
        if due.value is not None and due.kind == DueDateKind.EXACT:
            return format_ru_date(due.value), False
    return None, False


def _assignee_from_text(text: str) -> str | None:
    responsible = _RESPONSIBLE_RE.search(text)
    if responsible:
        person = find_person_name(responsible.group(1))
        return short_name(person[0]) if person else _clean(responsible.group(1)) or None
    person = find_person_name(text)
    return short_name(person[0]) if person else None


def _task_text(body: str) -> str:
    """Текст поручения без исполнителя в начале и без «Срок: …»/«Ответственный: …»."""
    text = _DUE_PHRASE_RE.sub("", body)
    text = _RESPONSIBLE_RE.sub("", text)
    person = find_person_name(text)
    if person and person[1] <= 2:
        text = text[person[2] :]
    cleaned = _clean(text).rstrip(".")
    return cleaned[:1].upper() + cleaned[1:] if cleaned else _clean(body)


def _archive_item_from_row(cells: list[str], protocol_date: str | None) -> ArchiveActionItem | None:
    meaningful = [cell for cell in cells if cell]
    if len(meaningful) < 2:
        return None
    header = normalize_text(" ".join(meaningful))
    if "поручени" in header and ("срок" in header or "ответствен" in header) and len(header) < 120:
        return None
    label: str | None = None
    if re.fullmatch(r"\d{1,2}(?:\.\d{1,2})*\.?", meaningful[0]):
        label = meaningful.pop(0).rstrip(".")
    due_date: str | None = None
    is_recurring = False
    assignee: str | None = None
    task_cells: list[str] = []
    for cell in meaningful:
        due, recurring = _due_from_text(cell, protocol_date)
        if (due or recurring) and len(cell) < 60 and due_date is None and not is_recurring:
            due_date, is_recurring = due, recurring
            continue
        person = find_person_name(cell)
        if person and assignee is None and len(cell) < 120:
            assignee = short_name(person[0])
            continue
        task_cells.append(cell)
    if not task_cells:
        return None
    task = max(task_cells, key=len)
    return ArchiveActionItem(
        item_label=label,
        task=task,
        assignee=assignee,
        due_date=due_date,
        is_recurring=is_recurring,
    )


def parse_archive_protocol(text: str, file_name: str) -> ArchiveProtocol:
    head_lines = [line for line in text.splitlines()[:15] if CELL_SEPARATOR not in line]
    head_lines = [line for line in head_lines if not _ARCHIVE_ITEM_RE.match(line)]
    head = "\n".join(head_lines)
    number_match = _PROTOCOL_NUMBER_RE.search(head)
    protocol_date = find_absolute_date(head)
    protocol_date_str = format_ru_date(protocol_date) if protocol_date else None

    items: list[ArchiveActionItem] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if CELL_SEPARATOR in line:
            item = _archive_item_from_row(
                [cell.strip() for cell in line.split(CELL_SEPARATOR.strip())], protocol_date_str
            )
            if item:
                items.append(item)
            continue
        match = _ARCHIVE_ITEM_RE.match(line)
        if not match or not _looks_like_task(match.group(2)):
            continue
        if normalize_text(match.group(2)).startswith(("о ", "об ", "обо ")):
            continue  # заголовок вопроса повестки, а не поручение
        body = match.group(2)
        due_date, is_recurring = _due_from_text(body, protocol_date_str)
        items.append(
            ArchiveActionItem(
                item_label=match.group(1),
                task=_task_text(body),
                assignee=_assignee_from_text(body),
                due_date=due_date,
                is_recurring=is_recurring,
            )
        )
    return ArchiveProtocol(
        file_name=file_name,
        protocol_number=number_match.group(1).rstrip(".") if number_match else None,
        protocol_date=protocol_date_str,
        action_items=items,
    )
