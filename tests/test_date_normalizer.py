from datetime import date

import pytest

from backend.app.services.date_normalizer import (
    DueDateKind,
    dates_mentioned,
    find_absolute_date,
    normalize_due_date,
)

MEETING = date(2026, 10, 20)  # вторник


@pytest.mark.parametrize(
    ("phrase", "expected", "kind"),
    [
        ("до 15 ноября", date(2026, 11, 15), DueDateKind.EXACT),
        ("до пятнадцатого ноября", date(2026, 11, 15), DueDateKind.EXACT),
        ("к двадцать пятому декабря", date(2026, 12, 25), DueDateKind.EXACT),
        ("до 15 января", date(2027, 1, 15), DueDateKind.EXACT),
        ("15.11.2026", date(2026, 11, 15), DueDateKind.EXACT),
        ("до 01.02.27", date(2027, 2, 1), DueDateKind.EXACT),
        ("срок до 18.11", date(2026, 11, 18), DueDateKind.EXACT),
        ("до 1 сентября", date(2027, 9, 1), DueDateKind.EXACT),
        ("до 5 марта 2027 года", date(2027, 3, 5), DueDateKind.EXACT),
        ("до 25 числа", date(2026, 10, 25), DueDateKind.RELATIVE),
        ("до 10 числа", date(2026, 11, 10), DueDateKind.RELATIVE),
        ("до конца недели", date(2026, 10, 23), DueDateKind.RELATIVE),
        ("до конца следующей недели", date(2026, 10, 30), DueDateKind.RELATIVE),
        ("до конца месяца", date(2026, 10, 31), DueDateKind.RELATIVE),
        ("до конца следующего месяца", date(2026, 11, 30), DueDateKind.RELATIVE),
        ("до конца квартала", date(2026, 12, 31), DueDateKind.RELATIVE),
        ("до конца следующего квартала", date(2027, 3, 31), DueDateKind.RELATIVE),
        ("до конца полугодия", date(2026, 12, 31), DueDateKind.RELATIVE),
        ("до конца года", date(2026, 12, 31), DueDateKind.RELATIVE),
        ("до конца учебного года", date(2027, 8, 31), DueDateKind.RELATIVE),
        ("до конца ноября", date(2026, 11, 30), DueDateKind.RELATIVE),
        ("к началу учебного года", date(2027, 9, 1), DueDateKind.RELATIVE),
        ("к началу декабря", date(2026, 12, 1), DueDateKind.RELATIVE),
        ("в течение недели", date(2026, 10, 27), DueDateKind.RELATIVE),
        ("в течение двух недель", date(2026, 11, 3), DueDateKind.RELATIVE),
        ("в течение 3 рабочих дней", date(2026, 10, 23), DueDateKind.RELATIVE),
        ("через пять дней", date(2026, 10, 25), DueDateKind.RELATIVE),
        ("через месяц", date(2026, 11, 20), DueDateKind.RELATIVE),
        ("в двухнедельный срок", date(2026, 11, 3), DueDateKind.RELATIVE),
        ("в десятидневный срок", date(2026, 10, 30), DueDateKind.RELATIVE),
        ("в месячный срок", date(2026, 11, 20), DueDateKind.RELATIVE),
        ("завтра", date(2026, 10, 21), DueDateKind.RELATIVE),
        ("послезавтра", date(2026, 10, 22), DueDateKind.RELATIVE),
        ("сегодня до конца дня", date(2026, 10, 20), DueDateKind.RELATIVE),
        ("к пятнице", date(2026, 10, 23), DueDateKind.RELATIVE),
        ("ко вторнику", date(2026, 10, 27), DueDateKind.RELATIVE),
        ("к следующей среде", date(2026, 10, 28), DueDateKind.RELATIVE),
        ("в 1 квартале 2027", date(2027, 3, 31), DueDateKind.RELATIVE),
        ("в первом квартале", date(2027, 3, 31), DueDateKind.RELATIVE),
        ("до IV квартала", date(2026, 12, 31), DueDateKind.RELATIVE),
        ("в ноябре", date(2026, 11, 30), DueDateKind.RELATIVE),
        ("до декабря", date(2026, 11, 30), DueDateKind.RELATIVE),
        ("ежемесячно до 5 числа", None, DueDateKind.RECURRING),
        ("постоянно", None, DueDateKind.RECURRING),
        ("в ближайшее время", None, DueDateKind.VAGUE),
        ("оперативно", None, DueDateKind.VAGUE),
        ("когда-нибудь потом", None, DueDateKind.UNRECOGNIZED),
        ("до 31 ноября", None, DueDateKind.UNRECOGNIZED),
        ("", None, DueDateKind.UNRECOGNIZED),
        (None, None, DueDateKind.UNRECOGNIZED),
    ],
)
def test_normalize_due_date(phrase: str | None, expected: date | None, kind: DueDateKind) -> None:
    result = normalize_due_date(phrase, MEETING)
    assert result.kind == kind
    assert result.value == expected
    assert result.is_resolved is (expected is not None)


def test_weekend_meeting_end_of_week_moves_forward() -> None:
    saturday = date(2026, 10, 24)
    assert normalize_due_date("до конца недели", saturday).value == date(2026, 10, 30)
    assert normalize_due_date("до конца первого полугодия", date(2026, 3, 1)).value == date(
        2026, 6, 30
    )
    assert normalize_due_date("до конца полугодия", date(2026, 3, 1)).value == date(2026, 6, 30)
    assert normalize_due_date("до конца следующего полугодия", date(2026, 3, 1)).value == date(
        2026, 12, 31
    )
    assert normalize_due_date("до конца следующего полугодия", MEETING).value == date(2027, 6, 30)
    assert normalize_due_date("до конца следующего года", MEETING).value == date(2027, 12, 31)
    assert normalize_due_date("до конца октября", date(2026, 11, 5)).value == date(2027, 10, 31)
    assert normalize_due_date("в сентябре", MEETING).value == date(2027, 9, 30)


def test_find_absolute_date_and_mentions() -> None:
    assert find_absolute_date("Протокол № 12 от «13» октября 2026 г.") == date(2026, 10, 13)
    assert find_absolute_date("от 13.10.2026") == date(2026, 10, 13)
    assert find_absolute_date("без даты") is None
    found = dates_mentioned("Петрову обеспечить готовность до пятнадцатого ноября.", MEETING)
    assert date(2026, 11, 15) in found
