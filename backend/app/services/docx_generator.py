"""Генератор Word-документа протокола на docxtpl (BE-102, DOC-01, DOC-02).

- Шаблон по умолчанию строится программно (Times New Roman 14, поля по ГОСТ Р 7.0.97),
  чтобы не хранить бинарный .docx в git и иметь воспроизводимую разметку.
- Пользовательский шаблон (бланк Министерства) должен содержать Jinja-поля docxtpl;
  перечень полей — в docs/backend/docx_template.md. Шаблон без полей или с ошибкой
  не ломает экспорт: используется шаблон по умолчанию, а пользователь получает предупреждение.
"""

import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from docx.text.paragraph import Paragraph
from docxtpl import DocxTemplate

from backend.app.core.config import Settings
from backend.app.schemas.protocol import ActionItem, ProtocolDraft, parse_ru_date

PLACEHOLDER = "[уточнить]"
FONT_NAME = "Times New Roman"
_MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
    "сентября", "октября", "ноября", "декабря",
)  # fmt: skip
_TEXT_WIDTH_CM = 16.5  # A4 21 см - левое поле 3 см - правое 1.5 см


class DocxGenerationError(RuntimeError):
    pass


def _sentence(text: str) -> str:
    cleaned = " ".join(text.split())
    if cleaned and cleaned[-1] not in ".!?…":
        cleaned += "."
    return cleaned


def _due_text(action: ActionItem) -> str:
    if action.due_date:
        return f"до {action.due_date}"
    if action.is_recurring and action.due_date_raw:
        raw = action.due_date_raw.strip()
        return raw[:1].upper() + raw[1:]
    if action.is_recurring:
        return "Постоянно"
    return PLACEHOLDER


def _long_date(value: str) -> str:
    parsed = parse_ru_date(value)
    return f"{parsed.day} {_MONTHS_GENITIVE[parsed.month - 1]} {parsed.year} г."


def build_context(draft: ProtocolDraft, settings: Settings) -> dict[str, Any]:
    """Контекст шаблона. Состав полей — публичный контракт для разметки бланка."""
    meta = draft.metadata
    attendees = [
        {
            "name": attendee.short_name,
            "full_name": attendee.full_name,
            "position": attendee.position or "",
        }
        for attendee in meta.attendees
    ]
    agenda: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    for item in draft.agenda_items:
        points: list[dict[str, str]] = []
        for decision in item.decisions:
            points.append(
                {
                    "number": f"{item.item_number}.{len(points) + 1}",
                    "text": _sentence(decision.text),
                }
            )
        for action in item.action_items:
            number = f"{item.item_number}.{len(points) + 1}"
            assignee = action.assignee or PLACEHOLDER
            due = _due_text(action)
            points.append(
                {
                    "number": number,
                    "text": f"{_sentence(action.task)} Срок: {due}. Ответственный: "
                    f"{_sentence(assignee)}",
                }
            )
            actions.append(
                {
                    "number": number,
                    "task": _sentence(action.task),
                    "assignee": assignee,
                    "assignee_role": action.assignee_role or "",
                    "due": due,
                }
            )
        agenda.append(
            {
                "number": item.item_number,
                "topic": item.topic,
                "reporter": item.reporter or "",
                "points": points,
            }
        )
    return {
        "org_name": settings.organization_name,
        "city": settings.city,
        "meeting_title": meta.meeting_title,
        "meeting_date": meta.meeting_date,
        "meeting_date_long": _long_date(meta.meeting_date),
        "protocol_number": meta.protocol_number or "____",
        "chairperson": meta.chairperson or PLACEHOLDER,
        "secretary": meta.secretary or PLACEHOLDER,
        "attendees": attendees,
        "attendees_text": ", ".join(a["name"] for a in attendees),
        "agenda": agenda,
        "actions": actions,
    }


def _set_font(run_or_style_font_element: Any) -> None:
    r_fonts = run_or_style_font_element.get_or_add_rFonts()
    for attribute in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        r_fonts.set(qn(attribute), FONT_NAME)


def _paragraph(
    document: Any,
    text: str = "",
    *,
    bold: bool = False,
    align: WD_ALIGN_PARAGRAPH | None = None,
    space_before: int = 0,
    first_line_indent: bool = False,
    label: str | None = None,
) -> Paragraph:
    paragraph: Paragraph = document.add_paragraph()
    if align is not None:
        paragraph.alignment = align
    paragraph.paragraph_format.space_before = Pt(space_before)
    if first_line_indent:
        paragraph.paragraph_format.first_line_indent = Cm(1.25)
    if label:
        paragraph.add_run(label).bold = True
    if text:
        paragraph.add_run(text).bold = bold
    return paragraph


def build_default_template(settings: Settings) -> bytes:
    del settings  # реквизиты организации подставляются полями шаблона
    document = Document()
    section = document.sections[0]
    section.page_height, section.page_width = Cm(29.7), Cm(21)
    section.top_margin, section.bottom_margin = Cm(2), Cm(2)
    section.left_margin, section.right_margin = Cm(3), Cm(1.5)

    normal = document.styles["Normal"]
    normal.font.name = FONT_NAME
    normal.font.size = Pt(14)
    _set_font(normal.element.get_or_add_rPr())
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = 1.0

    center, justify = WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.JUSTIFY
    _paragraph(document, "{{ org_name }}", bold=True, align=center)
    _paragraph(document, "ПРОТОКОЛ", bold=True, align=center, space_before=12)
    _paragraph(document, "{{ meeting_title }}", align=center)
    date_line = _paragraph(document, "{{ meeting_date }}\t№ {{ protocol_number }}", space_before=12)
    date_line.paragraph_format.tab_stops.add_tab_stop(Cm(_TEXT_WIDTH_CM), WD_TAB_ALIGNMENT.RIGHT)
    _paragraph(document, "{{ city }}", align=center)

    _paragraph(document, " {{ chairperson }}", label="Председатель:", space_before=12)
    _paragraph(document, " {{ secretary }}", label="Секретарь:")
    _paragraph(document, "Присутствовали:", bold=True, space_before=6)
    _paragraph(document, "{%p for a in attendees %}")
    _paragraph(document, "{{ a.name }}{% if a.position %} — {{ a.position }}{% endif %}")
    _paragraph(document, "{%p endfor %}")

    _paragraph(document, "ПОВЕСТКА ДНЯ:", bold=True, align=center, space_before=12)
    _paragraph(document, "{%p for item in agenda %}")
    _paragraph(
        document,
        "{{ item.number }}. {{ item.topic }}"
        "{% if item.reporter %} (докладчик: {{ item.reporter }}){% endif %}",
        align=justify,
    )
    _paragraph(document, "{%p endfor %}")

    _paragraph(document, "{%p for item in agenda %}")
    _paragraph(document, "{{ item.number }}. {{ item.topic }}", bold=True, space_before=12)
    _paragraph(document, "{%p if item.reporter %}")
    _paragraph(document, " {{ item.reporter }}", label="СЛУШАЛИ:")
    _paragraph(document, "{%p endif %}")
    _paragraph(document, "{%p if item.points %}")
    _paragraph(document, "РЕШИЛИ:", bold=True)
    _paragraph(document, "{%p endif %}")
    _paragraph(document, "{%p for point in item.points %}")
    _paragraph(
        document, "{{ point.number }}. {{ point.text }}", align=justify, first_line_indent=True
    )
    _paragraph(document, "{%p endfor %}")
    _paragraph(document, "{%p endfor %}")

    _paragraph(document, "ПЕРЕЧЕНЬ ПОРУЧЕНИЙ", bold=True, align=center, space_before=12)
    table = document.add_table(rows=4, cols=4)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    widths = (Cm(1.5), Cm(8.0), Cm(4.0), Cm(3.0))
    headers = ("№ п/п", "Поручение", "Ответственный", "Срок исполнения")
    cells_text = (
        (headers, True),
        (("{%tr for a in actions %}", "", "", ""), False),
        (("{{ a.number }}", "{{ a.task }}", "{{ a.assignee }}", "{{ a.due }}"), False),
        (("{%tr endfor %}", "", "", ""), False),
    )
    for row, (texts, bold) in zip(table.rows, cells_text, strict=True):
        for cell, text, width in zip(row.cells, texts, widths, strict=True):
            cell.width = width
            cell.paragraphs[0].add_run(text).bold = bold

    signature = _paragraph(document, "Председатель\t{{ chairperson }}", space_before=24)
    signature.paragraph_format.tab_stops.add_tab_stop(Cm(_TEXT_WIDTH_CM), WD_TAB_ALIGNMENT.RIGHT)
    secretary = _paragraph(document, "Секретарь\t{{ secretary }}", space_before=12)
    secretary.paragraph_format.tab_stops.add_tab_stop(Cm(_TEXT_WIDTH_CM), WD_TAB_ALIGNMENT.RIGHT)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def template_has_placeholders(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    except (zipfile.BadZipFile, KeyError, OSError):
        return False
    return "{{" in xml or "{%" in xml


def _render(template_source: Path | BytesIO, context: dict[str, Any], output_path: Path) -> None:
    template = DocxTemplate(template_source)
    template.render(context, autoescape=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    template.save(str(output_path))


class DocxGenerator:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def render(
        self, draft: ProtocolDraft, output_path: Path, custom_template: Path | None = None
    ) -> list[str]:
        """Формирует .docx; возвращает предупреждения (например, о непригодном шаблоне)."""
        warnings: list[str] = []
        context = build_context(draft, self._settings)
        if custom_template is not None:
            if template_has_placeholders(custom_template):
                try:
                    _render(custom_template, context, output_path)
                    return warnings
                except Exception as exc:  # noqa: BLE001 — любой сбой шаблона -> бланк по умолчанию
                    warnings.append(
                        f"Ошибка в загруженном шаблоне ({exc}). Использован шаблон по умолчанию."
                    )
            else:
                warnings.append(
                    "Загруженный шаблон не содержит полей {{ … }} для подстановки — использован "
                    "шаблон по умолчанию. Разметка бланка: docs/backend/docx_template.md."
                )
        try:
            _render(BytesIO(build_default_template(self._settings)), context, output_path)
        except Exception as exc:
            raise DocxGenerationError(f"Не удалось сформировать документ: {exc}") from exc
        return warnings
