from pathlib import Path

import pytest
from docx import Document

from backend.app.core.text import find_person_name, short_name, similarity
from backend.app.schemas.protocol import Attendee
from backend.app.services.attendee_matcher import AttendeeMatcher, same_person
from backend.app.services.document_parser import (
    DocumentParseError,
    extract_text,
    parse_agenda,
    parse_archive_protocol,
    parse_attendees,
)
from tests.conftest import AGENDA_TXT, ATTENDEES_TXT


def test_short_name_variants() -> None:
    assert short_name("Иванов Иван Иванович") == "Иванов И.И."
    assert short_name("И.И. Иванов") == "Иванов И.И."
    assert short_name("Иванов И. И.") == "Иванов И.И."
    assert short_name("отдел общего образования") == "отдел общего образования"
    assert find_person_name("без имени") is None
    assert similarity("", "текст") == 0.0


def test_parse_attendees_text() -> None:
    attendees, chair, secretary = parse_attendees(ATTENDEES_TXT)
    assert [a.short_name for a in attendees] == [
        "Иванов И.И.",
        "Петров П.П.",
        "Сидорова С.С.",
        "Кузнецова А.В.",
    ]
    assert attendees[1].position == "начальник отдела контроля качества образования"
    assert chair == "Иванов И.И."
    assert secretary == "Кузнецова А.В."


def test_parse_attendees_position_first_and_initials() -> None:
    text = "1. Министр образования — Иванов Иван Иванович\n2) Петров П.П., директор ИРО\nбез ФИО"
    attendees, chair, _ = parse_attendees(text)
    assert [(a.short_name, a.position) for a in attendees] == [
        ("Иванов И.И.", "Министр образования"),
        ("Петров П.П.", "директор ИРО"),
    ]
    assert chair is None


def test_parse_agenda_numbered_with_reporters_and_wrap() -> None:
    text = (
        "ПОВЕСТКА\n1. О подготовке к ГИА\nв 2027 году\nДокладчик: Петров Петр Петрович\n"
        "2) Разное (докладчик: Иванов И.И.)\n"
    )
    topics = parse_agenda(text)
    assert [(t.number, t.title, t.reporter) for t in topics] == [
        (1, "О подготовке к ГИА в 2027 году", "Петров П.П."),
        (2, "Разное", "Иванов И.И."),
    ]
    assert parse_agenda(AGENDA_TXT)[0].reporter == "Петров П.П."


def test_parse_agenda_without_numbers() -> None:
    topics = parse_agenda("Повестка\nО бюджете\nО кадрах")
    assert [t.title for t in topics] == ["О бюджете", "О кадрах"]


def test_parse_archive_paragraphs_and_tables(tmp_path: Path) -> None:
    protocol = parse_archive_protocol(
        "ПРОТОКОЛ № 5 от «01» сентября 2026 г.\n"
        "1. О подготовке к учебному году\n"
        "1.1. Обеспечить готовность школ. Ответственный: Петров П.П. Срок: 15.09.2026.\n"
        "1.2. Представлять отчеты ежемесячно\n",
        "p5.txt",
    )
    assert protocol.protocol_number == "5"
    assert protocol.protocol_date == "01.09.2026"
    assert protocol.label == "Протокол № 5 от 01.09.2026"
    assert [(i.item_label, i.task, i.assignee, i.due_date) for i in protocol.action_items] == [
        ("1.1", "Обеспечить готовность школ", "Петров П.П.", "15.09.2026"),
        ("1.2", "Представлять отчеты ежемесячно", None, None),
    ]
    assert protocol.action_items[1].is_recurring is True

    document = Document()
    document.add_paragraph("ПРОТОКОЛ № 6")
    table = document.add_table(rows=3, cols=4)
    for row, values in zip(
        table.rows,
        [
            ("№ п/п", "Поручение", "Ответственный", "Срок исполнения"),
            ("2.1", "Провести мониторинг питания в школах", "Сидорова С.С.", "до 01.11.2026"),
            ("2.2", "Подготовить справку", "", ""),
        ],
        strict=True,
    ):
        for cell, value in zip(row.cells, values, strict=True):
            cell.text = value
    path = tmp_path / "p6.docx"
    document.save(str(path))
    parsed = parse_archive_protocol(extract_text(path), "p6.docx")
    assert parsed.label == "Протокол № 6"
    assert [(i.item_label, i.task, i.assignee, i.due_date) for i in parsed.action_items] == [
        ("2.1", "Провести мониторинг питания в школах", "Сидорова С.С.", "01.11.2026"),
        ("2.2", "Подготовить справку", None, None),
    ]
    assert parse_archive_protocol("Текст", "x.txt").label == "Протокол «x.txt»"


def test_extract_text_formats(tmp_path: Path) -> None:
    cp1251 = tmp_path / "list.txt"
    cp1251.write_bytes("Иванов Иван Иванович".encode("cp1251"))
    assert extract_text(cp1251) == "Иванов Иван Иванович"

    document = Document()
    document.add_paragraph("Иванов Иван Иванович")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Петров Петр Петрович"
    table.rows[0].cells[1].text = "директор"
    docx_path = tmp_path / "list.docx"
    document.save(str(docx_path))
    attendees, _, _ = parse_attendees(extract_text(docx_path))
    assert [(a.short_name, a.position) for a in attendees] == [
        ("Иванов И.И.", None),
        ("Петров П.П.", "директор"),
    ]

    with pytest.raises(DocumentParseError, match="не поддерживается"):
        extract_text(tmp_path / "file.doc")
    broken = tmp_path / "broken.docx"
    broken.write_bytes(b"not a zip")
    with pytest.raises(DocumentParseError, match="Не удалось прочитать"):
        extract_text(broken)
    broken_pdf = tmp_path / "broken.pdf"
    broken_pdf.write_bytes(b"not a pdf")
    with pytest.raises(DocumentParseError):
        extract_text(broken_pdf)


def test_attendee_matcher_cases_and_ambiguity() -> None:
    attendees = [
        Attendee(full_name="Иванов Иван Иванович", position="министр"),
        Attendee(full_name="Иванова Мария Петровна", position="заместитель министра"),
        Attendee(
            full_name="Зинин Сергей Александрович", position="начальник отдела общего образования"
        ),
        Attendee(full_name="Петров П.П."),
    ]
    matcher = AttendeeMatcher(attendees)
    assert matcher.resolve("Зинину").assignee == "Зинин С.А."
    assert matcher.resolve("Сергею Александровичу").assignee == "Зинин С.А."
    assert matcher.resolve("Петрову").assignee == "Петров П.П."
    assert matcher.resolve("Иванову И.И.").assignee == "Иванов И.И."
    assert matcher.resolve("Марии Петровне").assignee == "Иванова М.П."
    assert matcher.resolve("начальнику отдела общего образования").assignee == "Зинин С.А."
    ambiguous = matcher.resolve("Ивановой")
    assert ambiguous.ambiguous and set(ambiguous.candidates) == {"Иванов И.И.", "Иванова М.П."}
    unknown = matcher.resolve("управлению образования")
    assert unknown.assignee == "управлению образования" and not unknown.matched
    assert matcher.resolve(None).assignee is None
    assert matcher.role_of("Иванов И.И.") == "министр"
    assert matcher.role_of("Нет") is None
    assert matcher.mentioned_in("Зинин С.А.", "Сергей Александрович, подготовьте") is True
    assert matcher.mentioned_in("Нет Н.Н.", "текст") is False
    assert AttendeeMatcher([]).resolve("Петрову").assignee == "Петрову"


def test_same_person() -> None:
    assert same_person("Сидоровой С.С.", "Сидорова С.С.")
    assert not same_person("Сидоровой А.А.", "Сидорова С.С.")
    assert not same_person("Петров П.П.", "Сидорова С.С.")
    assert not same_person(None, "Сидорова С.С.")
    assert same_person("ИРО", "иро")
