import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from backend.app.core.config import Settings
from backend.app.schemas.documents import (
    AgendaTopic,
    ArchiveActionItem,
    ArchiveProtocol,
    MeetingContext,
)
from backend.app.schemas.protocol import (
    ActionItem,
    AgendaItem,
    Attendee,
    ProtocolDraft,
    ProtocolMetadata,
)
from backend.app.schemas.transcription import MeetingTranscription
from backend.app.services.analytics import AnalyticsEngine
from backend.app.services.attendee_matcher import AttendeeMatcher
from backend.app.services.document_parser import DocumentParseError
from backend.app.services.extraction import (
    CHUNK_RESPONSE_SCHEMA,
    ProtocolExtractor,
    build_context_block,
)
from backend.app.services.gigachat_client import (
    GigaChatClient,
    GigaChatError,
    GigaChatUnavailableError,
)
from backend.app.services.interfaces import LLMResponseError, parse_json_object
from backend.app.services.protocol_builder import ProtocolBuilder
from backend.app.services.refinement import DraftRefiner, describe_draft
from backend.app.services.transcript import (
    TranscriptIndex,
    chunk_transcript,
    ensure_segments,
    format_timecode,
    load_transcript_file,
    transcription_from_text,
)
from tests.conftest import EXTRACTION_RESPONSE, FakeLLM, make_transcription

MEETING = date(2026, 10, 20)


# --- стенограмма ---
def test_transcript_import_chunking_and_grounding(tmp_path: Path) -> None:
    text = "[00:00:05] Добрый день. Начинаем.\n00:01:10 — Петрову подготовить отчет до пятницы.\n"
    transcription = transcription_from_text(text, "steno.txt")
    assert [s.text for s in transcription.segments] == [
        "Добрый день.",
        "Начинаем.",
        "Петрову подготовить отчет до пятницы.",
    ]
    assert transcription.segments[2].start == 70.0
    assert format_timecode(3725) == "01:02:05"

    chunks = chunk_transcript(make_transcription(), max_chars=200, overlap_segments=1)
    assert len(chunks) > 1
    assert chunks[1].first_segment <= chunks[0].last_segment  # перекрытие
    assert chunks[-1].last_segment == 9

    index = TranscriptIndex(make_transcription())
    near = index.locate("Петрову обеспечить готовность всех пунктов проведения экзаменов", [4])
    assert near.grounded and near.segment_ids == [4] and near.start == 40.0
    far = index.locate("обновить инструкции для наблюдателей", [0])
    assert far.grounded and far.segment_ids == [5]
    assert not index.locate("Смирнову провести проверку совместно с Рособрнадзором").grounded
    assert not index.locate(None).grounded
    assert not index.locate("да").grounded
    assert index.search("олимпиады отчет", top_k=2) == [7, 8]
    assert index.contains("Петрову Петру Петровичу")
    assert index.window_text([]) == ""

    json_path = tmp_path / "t.json"
    json_path.write_text(make_transcription().model_dump_json(), encoding="utf-8")
    assert len(load_transcript_file(json_path, "t.json").segments) == 10
    json_path.write_text('{"bad": 1}', encoding="utf-8")
    with pytest.raises(DocumentParseError, match="MeetingTranscription"):
        load_transcript_file(json_path, "t.json")
    empty = tmp_path / "empty.txt"
    empty.write_text("   \n", encoding="utf-8")
    with pytest.raises(DocumentParseError, match="не содержит текста"):
        load_transcript_file(empty, "empty.txt")

    no_segments = MeetingTranscription(model="m", source="s", text="Раз. Два.", segments=[])
    assert len(ensure_segments(no_segments).segments) == 2


# --- LLM: разбор ответов ---
def test_parse_json_object_variants() -> None:
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Вот ответ: {"a": 2} конец') == {"a": 2}
    for bad in ("нет json", "{oops}", "[1, 2]"):
        with pytest.raises(LLMResponseError):
            parse_json_object(bad)


def test_extractor_retries_skips_bad_items_and_marks_failed_chunks() -> None:
    responses = iter(
        [
            "не JSON",  # первая попытка чанка 1
            json.dumps(
                {
                    "decisions": [{"text": "ок", "quote": None}, "мусор"],
                    "action_items": [
                        {
                            "agenda_item": "2",
                            "task": "Подготовить отчет об итогах олимпиады",
                            "assignee_mention": "null",
                            "due_date_mention": "",
                            "quote": "подготовить отчет об итогах олимпиады",
                            "segment_ids": "8",
                        },
                        {"task": "Подготовить отчет об итогах олимпиады", "segment_ids": [8]},
                    ],
                    "reports": [{"agenda_item": True, "reporter_mention": "Петров"}],
                }
            ),
            "мусор",  # чанк 2: обе попытки неудачны
            "мусор",
        ]
    )
    llm = FakeLLM(extraction=lambda _: next(responses))
    settings = Settings(llm_chunk_chars=500, llm_chunk_overlap_segments=0)
    progress: list[tuple[int, int]] = []
    result = ProtocolExtractor(llm, settings).extract(
        make_transcription(),
        MeetingContext(),
        "20.10.2026",
        on_progress=lambda done, total: progress.append((done, total)),
    )
    assert progress == [(1, 2), (2, 2)]
    assert len(result.action_items) == 1  # дубль отброшен
    action = result.action_items[0]
    assert action.agenda_item == 2 and action.segment_ids == [8]
    assert action.assignee_mention is None and action.due_date_mention is None
    assert result.decisions == []  # «ок» короче 3 символов
    assert result.reports[0].agenda_item is None
    assert len(result.failed_chunks) == 1
    assert llm.calls[0]["json_schema"] == CHUNK_RESPONSE_SCHEMA


def test_extractor_propagates_unavailability_and_tolerates_upstream_errors() -> None:
    with pytest.raises(GigaChatUnavailableError):
        ProtocolExtractor(FakeLLM(available=False), Settings()).extract(
            make_transcription(), MeetingContext(), "20.10.2026"
        )

    def broken(_: str) -> str:
        raise GigaChatError("HTTP 500")

    result = ProtocolExtractor(FakeLLM(extraction=broken), Settings()).extract(
        make_transcription(), MeetingContext(), "20.10.2026"
    )
    assert len(result.failed_chunks) == 1


def test_context_block_mentions_agenda_and_attendees() -> None:
    context = MeetingContext(
        attendees=[Attendee(full_name="Петров Петр Петрович", position="начальник")],
        agenda=[AgendaTopic(number=1, title="О ГИА", reporter="Петров П.П.")],
    )
    block = build_context_block(context, "20.10.2026")
    assert "- Петров П.П. — начальник" in block
    assert "1. О ГИА (докладчик: Петров П.П.)" in block
    assert "Повестка не загружена" in build_context_block(MeetingContext(), "20.10.2026")


# --- сборка без повестки и в режиме «не отбрасывать» ---
def test_builder_without_agenda_groups_by_topic_and_keeps_ungrounded() -> None:
    llm_payload: dict[str, Any] = {
        "decisions": [],
        "action_items": [
            {**EXTRACTION_RESPONSE["action_items"][0], "agenda_item": None, "topic": "ГИА"},
            {**EXTRACTION_RESPONSE["action_items"][2], "agenda_item": None, "topic": None},
            {**EXTRACTION_RESPONSE["action_items"][4], "agenda_item": None, "topic": "гиа"},
        ],
        "reports": [],
    }
    llm = FakeLLM(extraction=lambda _: json.dumps(llm_payload))
    settings = Settings(drop_ungrounded_items=False)
    extraction = ProtocolExtractor(llm, settings).extract(
        make_transcription(), MeetingContext(), "20.10.2026"
    )
    builder = ProtocolBuilder(
        TranscriptIndex(make_transcription()), AttendeeMatcher([]), MEETING, settings
    )
    built = builder.build(extraction, MeetingContext())
    assert [item.topic for item in built.agenda_items] == ["ГИА", "Общие вопросы"]
    gia = built.agenda_items[0].action_items
    assert len(gia) == 2
    assert gia[1].source_start is None  # неподтверждённое оставлено без таймкода
    assert gia[1].due_date is None and gia[1].assignee is None  # упоминания не в цитате
    assert built.notes == []

    misc = ProtocolBuilder(
        TranscriptIndex(make_transcription()), AttendeeMatcher([]), MEETING, Settings()
    ).build(
        extraction.__class__(action_items=[extraction.action_items[1]]),
        MeetingContext(agenda=[AgendaTopic(number=1, title="Бюджет школ")]),
    )
    assert [item.topic for item in misc.agenda_items] == ["Бюджет школ", "Разное"]


# --- аналитика ---
def _draft(*actions: ActionItem) -> ProtocolDraft:
    return ProtocolDraft(
        session_id="s",
        metadata=ProtocolMetadata(meeting_date="20.10.2026"),
        agenda_items=[AgendaItem(item_number=1, topic="Вопрос", action_items=list(actions))],
    )


def test_analytics_contradictions_and_risks() -> None:
    draft = _draft(
        ActionItem(
            task="Подготовить отчет по питанию", assignee="Петров П.П.", due_date="22.10.2026"
        ),
        ActionItem(
            task="Подготовить отчет по питанию", assignee="Сидорова С.С.", due_date="25.10.2026"
        ),
        ActionItem(
            task="Провести семинар для директоров", assignee="Петров П.П.", due_date="10.10.2026"
        ),
        ActionItem(
            task="Провести семинар для директоров", assignee="Петров П.П.", due_date="10.10.2026"
        ),
        ActionItem(task="Обновить сайт", assignee="Петров П.П.", due_date="24.10.2026"),
        ActionItem(task="Направить письмо", assignee="Петров П.П.", is_recurring=True),
        ActionItem(task="Собрать заявки", assignee="Неизвестный Н.Н.", due_date="01.12.2026"),
    )
    archive = [
        ArchiveProtocol(
            file_name="p.txt",
            protocol_number="9",
            action_items=[
                ArchiveActionItem(
                    item_label="3", task="Обновить сайт министерства", assignee="Сидоровой С.С."
                ),
                ArchiveActionItem(
                    task="Собрать заявки школ", assignee="Неизвестный Н.Н.", due_date="15.12.2026"
                ),
            ],
        )
    ]
    matcher = AttendeeMatcher(
        [
            Attendee(full_name="Петров Петр Петрович"),
            Attendee(full_name="Сидорова Светлана Сергеевна"),
        ]
    )
    report = AnalyticsEngine(Settings(assignee_overload_threshold=4)).analyze(
        draft, archive, matcher, input_warnings=["Файл не разобран"]
    )
    risk_types = {risk.type.value for risk in report.risks}
    assert {
        "TIGHT_DEADLINE",
        "DEADLINE_IN_PAST",
        "WEEKEND_DEADLINE",
        "ASSIGNEE_OVERLOAD",
        "DUPLICATE_ITEM",
    } <= risk_types
    scopes = [c.scope.value for c in report.contradictions]
    assert scopes.count("meeting") == 1 and scopes.count("archive") == 2
    meeting = next(c for c in report.contradictions if c.scope.value == "meeting")
    assert "п. 1.1 и п. 1.2" in meeting.description
    gap_types = [gap.type.value for gap in report.gaps]
    assert "UNMATCHED_ASSIGNEE" in gap_types and "MISSING_INPUT" in gap_types
    assert "MISSING_DUE_DATE" not in gap_types  # периодическое поручение — не пробел


def test_analytics_agenda_without_decisions_and_ambiguous_assignee() -> None:
    draft = ProtocolDraft(
        session_id="s",
        metadata=ProtocolMetadata(meeting_date="20.10.2026"),
        agenda_items=[
            AgendaItem(item_number=1, topic="Без решения"),
            AgendaItem(
                item_number=2,
                topic="Кадры",
                action_items=[ActionItem(task="Подготовить приказ", assignee_raw="Иванову")],
            ),
        ],
    )
    matcher = AttendeeMatcher(
        [Attendee(full_name="Иванов Иван Иванович"), Attendee(full_name="Иванова Анна Сергеевна")]
    )
    report = AnalyticsEngine(Settings()).analyze(draft, [], matcher)
    gap_types = [gap.type.value for gap in report.gaps]
    assert gap_types[:3] == [
        "NO_DECISION_FOR_AGENDA_ITEM",
        "MISSING_DUE_DATE",
        "AMBIGUOUS_ASSIGNEE",
    ]


# --- ИИ-правки ---
def test_refiner_operations() -> None:
    transcription = make_transcription()
    index = TranscriptIndex(transcription)
    matcher = AttendeeMatcher([Attendee(full_name="Петров Петр Петрович")])
    builder = ProtocolBuilder(index, matcher, MEETING, Settings())
    keep = ActionItem(task="Обеспечить готовность пунктов", assignee="Петров П.П.")
    drop = ActionItem(task="Лишнее поручение")
    draft = ProtocolDraft(
        session_id="s",
        metadata=ProtocolMetadata(meeting_date="20.10.2026"),
        agenda_items=[
            AgendaItem(
                item_number=1,
                topic="ГИА",
                decisions=[],
                action_items=[keep, drop],
            )
        ],
    )
    from backend.app.schemas.protocol import Decision

    decision = Decision(text="Принять к сведению")
    draft.agenda_items[0].decisions.append(decision)
    assert f"[{keep.id}] 1.2 Поручение" in describe_draft(draft)

    operations = [
        {
            "op": "update_action_item",
            "target_id": keep.id,
            "text": "Обеспечить готовность ППЭ",
            "due_date_mention": "до 1 декабря",
        },
        {"op": "update_action_item", "target_id": "act-none"},
        {"op": "update_action_item", "target_id": keep.id, "assignee_mention": "Смирнову"},
        {"op": "delete_action_item", "target_id": drop.id},
        {"op": "delete_action_item", "target_id": "act-none"},
        {
            "op": "add_action_item",
            "agenda_item": 1,
            "text": "Обновить инструкции для наблюдателей",
            "quote": "Также надо обновить инструкции для наблюдателей.",
            "segment_ids": [5],
        },
        {
            "op": "add_action_item",
            "agenda_item": 9,
            "text": "Провести совещание с директорами школ",
        },
        {"op": "add_action_item", "text": None},
        {
            "op": "update_decision",
            "target_id": decision.id,
            "text": "Информацию принять к сведению",
        },
        {"op": "update_decision", "target_id": "dec-none", "text": "x"},
        {
            "op": "add_decision",
            "agenda_item": 1,
            "text": "Принять информацию",
            "quote": "Решили информацию принять к сведению.",
            "segment_ids": [3],
        },
        {"op": "add_decision", "agenda_item": 1, "text": "Одобрить план закупок"},
        {"op": "add_decision", "text": None},
        {"op": "set_reporter", "agenda_item": 1, "text": "Петрову Петру Петровичу"},
        {"op": "set_reporter", "agenda_item": 7, "text": "Петрову"},
        {"op": "set_reporter", "agenda_item": 1, "text": "Козлову"},
        {"op": "set_reporter", "text": None},
        {"op": "delete_decision", "target_id": decision.id},
        {"op": "delete_decision", "target_id": "dec-none"},
        {"op": "unknown_op"},
        "мусор",
    ]
    llm = FakeLLM(refine=lambda _: json.dumps({"operations": operations}))
    refiner = DraftRefiner(llm, builder, index, matcher, MEETING, Settings())
    feedback = "Перенеси срок до 1 декабря, добавь поручение провести совещание с директорами школ"
    outcome = refiner.refine(draft, feedback)

    item = outcome.draft.agenda_items[0]
    updated = item.action_items[0]
    assert updated.task == "Обеспечить готовность ППЭ" and updated.due_date == "01.12.2026"
    assert updated.assignee == "Петров П.П."  # «Смирнову» не подтверждён
    assert [a.task for a in item.action_items][1] == "Обновить инструкции для наблюдателей"
    misc = outcome.draft.agenda_items[1]
    assert misc.topic == "Разное" and misc.action_items[0].origin.value == "manual"
    assert item.reporter == "Петров П.П."
    assert [d.text for d in item.decisions] == ["Принять информацию"]
    assert len(outcome.applied) == 8
    assert len(outcome.rejected) == 11
    assert draft.agenda_items[0].action_items[1] is drop  # исходный черновик не мутирован

    bad = DraftRefiner(
        FakeLLM(refine=lambda _: "не json"), builder, index, matcher, MEETING, Settings()
    )
    with pytest.raises(LLMResponseError):
        bad.refine(draft, "правка")


# --- клиент GigaChat: строгий JSON ---
def test_gigachat_client_sends_json_schema() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["response_format"] == {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": {"type": "object"}},
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    client = GigaChatClient(
        base_url="http://127.0.0.1:8080", transport=httpx.MockTransport(handler)
    )
    try:
        assert client.chat("x", json_schema={"type": "object"}) == "{}"
    finally:
        client.close()
