"""Общие фикстуры: изолированное хранилище, фейковые STT/LLM и синтетическое совещание.

Все данные синтетические (условные ФИО), реальные материалы Министерства в тестах не используются.
"""

import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from backend.app.api.dependencies import AppServices, create_services, set_services
from backend.app.core.config import Settings
from backend.app.schemas.transcription import (
    DomainVocabulary,
    MeetingTranscription,
    TranscriptionSegment,
)
from backend.app.services.extraction import EXTRACTION_SYSTEM_PROMPT
from backend.app.services.gigachat_client import GigaChatUnavailableError
from backend.app.services.interfaces import InlineJobRunner
from backend.app.services.refinement import REFINE_SYSTEM_PROMPT

MEETING_DATE = "20.10.2026"  # вторник

SEGMENT_TEXTS = [
    "Добрый день, коллеги. Начинаем аппаратное совещание.",
    "Первый вопрос о готовности к государственной итоговой аттестации. Слово Петрову Петру Петровичу.",
    "Пункты проведения экзаменов готовы на девяносто процентов.",
    "Решили информацию принять к сведению.",
    "Петрову обеспечить готовность всех пунктов проведения экзаменов до пятнадцатого ноября.",
    "Также надо обновить инструкции для наблюдателей.",
    "Сидорова предложила перенести семинар, но решение не приняли, обсудим позже.",
    "Второй вопрос об итогах региональной олимпиады.",
    "Сидоровой Светлане Сергеевне подготовить отчет об итогах олимпиады к следующей пятнице.",
    "Иванову Ивану Ивановичу направить письмо в муниципалитеты в ближайшее время.",
]

ATTENDEES_TXT = """Список участников
Председатель: Иванов Иван Иванович — министр образования
Петров Петр Петрович — начальник отдела контроля качества образования
Сидорова Светлана Сергеевна — начальник отдела общего образования
Секретарь: Кузнецова Анна Викторовна — консультант
"""

AGENDA_TXT = """Повестка совещания
1. О готовности к государственной итоговой аттестации (докладчик: Петров П.П.)
2. Об итогах региональной олимпиады
"""

ARCHIVE_TXT = """ПРОТОКОЛ № 11 от 13.10.2026
1. Сидоровой С.С. подготовить отчет об итогах олимпиады. Срок: до 16.10.2026.
"""


def make_transcription(texts: list[str] | None = None) -> MeetingTranscription:
    texts = texts or SEGMENT_TEXTS
    segments = [
        TranscriptionSegment(start=float(i * 10), end=float(i * 10 + 9), text=text)
        for i, text in enumerate(texts)
    ]
    return MeetingTranscription(
        model="e2e_rnnt",
        source="meeting.mp3",
        text=" ".join(texts),
        segments=segments,
    )


EXTRACTION_RESPONSE: dict[str, Any] = {
    "decisions": [
        {
            "agenda_item": 1,
            "topic": None,
            "text": "Принять информацию к сведению",
            "quote": "Решили информацию принять к сведению.",
            "segment_ids": [3],
        },
        {  # выдуманное решение — цитаты нет в стенограмме
            "agenda_item": 2,
            "topic": None,
            "text": "Утвердить новый состав жюри",
            "quote": "Утвердили новый состав жюри олимпиады единогласно.",
            "segment_ids": [7],
        },
    ],
    "action_items": [
        {
            "agenda_item": 1,
            "topic": None,
            "task": "Обеспечить готовность всех пунктов проведения экзаменов",
            "assignee_mention": "Петрову",
            "due_date_mention": "до пятнадцатого ноября",
            "quote": "Петрову обеспечить готовность всех пунктов проведения экзаменов "
            "до пятнадцатого ноября.",
            "segment_ids": [4],
        },
        {
            "agenda_item": 1,
            "topic": None,
            "task": "Обновить инструкции для наблюдателей",
            "assignee_mention": None,
            "due_date_mention": "до 30 ноября",  # срок не звучал — должен быть отброшен
            "quote": "Также надо обновить инструкции для наблюдателей.",
            "segment_ids": [5],
        },
        {
            "agenda_item": 2,
            "topic": None,
            "task": "Подготовить отчет об итогах олимпиады",
            "assignee_mention": "Сидоровой Светлане Сергеевне",
            "due_date_mention": "к следующей пятнице",
            "quote": "Сидоровой Светлане Сергеевне подготовить отчет об итогах олимпиады "
            "к следующей пятнице.",
            "segment_ids": [8],
        },
        {
            "agenda_item": 2,
            "topic": None,
            "task": "Направить письмо в муниципалитеты",
            "assignee_mention": "Иванову Ивану Ивановичу",
            "due_date_mention": "в ближайшее время",
            "quote": "Иванову Ивану Ивановичу направить письмо в муниципалитеты в ближайшее время.",
            "segment_ids": [9],
        },
        {  # галлюцинация: такого поручения в стенограмме нет
            "agenda_item": 1,
            "topic": None,
            "task": "Провести проверку пунктов совместно с Рособрнадзором",
            "assignee_mention": "Смирнову",
            "due_date_mention": "до первого декабря",
            "quote": "Смирнову провести проверку совместно с Рособрнадзором до первого декабря.",
            "segment_ids": [2],
        },
    ],
    "reports": [{"agenda_item": 1, "reporter_mention": "Петрову Петру Петровичу"}],
}

_ACTION_ID_RE = re.compile(r"\[(act-[0-9a-f]+)\] [\d.]+ Поручение: Обновить инструкции")


def default_refine_response(prompt: str) -> dict[str, Any]:
    match = _ACTION_ID_RE.search(prompt)
    target = match.group(1) if match else None
    return {
        "operations": [
            {
                "op": "update_action_item",
                "target_id": target,
                "agenda_item": None,
                "text": None,
                "assignee_mention": "Сидорова",
                "due_date_mention": "до 25 ноября",
                "quote": None,
                "segment_ids": [],
            },
            {  # не подтверждено ни стенограммой, ни замечанием — должно быть отклонено
                "op": "add_action_item",
                "target_id": None,
                "agenda_item": 2,
                "text": "Закупить оборудование для лабораторий",
                "assignee_mention": None,
                "due_date_mention": None,
                "quote": "Закупить оборудование до конца года.",
                "segment_ids": [],
            },
        ]
    }


class FakeLLM:
    def __init__(
        self,
        extraction: Callable[[str], str] | None = None,
        refine: Callable[[str], str] | None = None,
        available: bool = True,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.available = available
        self._extraction = extraction or (lambda _: json.dumps(EXTRACTION_RESPONSE))
        self._refine = refine or (lambda prompt: json.dumps(default_refine_response(prompt)))

    def health(self) -> None:
        if not self.available:
            raise GigaChatUnavailableError("Локальный сервер GigaChat недоступен: refused")

    def chat(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 512,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        self.calls.append(
            {"prompt": prompt, "system_prompt": system_prompt, "json_schema": json_schema}
        )
        if not self.available:
            raise GigaChatUnavailableError("Локальный сервер GigaChat недоступен: refused")
        if system_prompt == REFINE_SYSTEM_PROMPT:
            return self._refine(prompt)
        assert system_prompt == EXTRACTION_SYSTEM_PROMPT
        return self._extraction(prompt)


class FakeTranscriber:
    def __init__(self, transcription: MeetingTranscription | None = None) -> None:
        self.transcription = transcription or make_transcription()
        self.calls: list[tuple[Path, DomainVocabulary | None]] = []

    def transcribe(
        self, audio_path: str | Path, vocabulary: DomainVocabulary | None = None
    ) -> MeetingTranscription:
        self.calls.append((Path(audio_path), vocabulary))
        return self.transcription


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data")


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def fake_transcriber() -> FakeTranscriber:
    return FakeTranscriber()


@pytest.fixture(autouse=True)
def services(
    settings: Settings, fake_llm: FakeLLM, fake_transcriber: FakeTranscriber
) -> Iterator[AppServices]:
    app_services = create_services(
        settings=settings,
        transcriber_factory=lambda: fake_transcriber,
        llm_factory=lambda: fake_llm,
        runner=InlineJobRunner(),
    )
    set_services(app_services)
    yield app_services
    set_services(None)
