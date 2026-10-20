"""Работа со стенограммой: импорт текста, нарезка на чанки для LLM, проверка цитат.

`TranscriptIndex.locate` — ключевой механизм защиты от галлюцинаций: каждое
решение и поручение должно опираться на цитату, которая реально присутствует
в стенограмме. Цитата, не найденная в тексте, считается выдуманной.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from backend.app.core.text import contains_all_stems, ordered_support, stems
from backend.app.schemas.transcription import MeetingTranscription, TranscriptionSegment
from backend.app.services.document_parser import DocumentParseError, extract_text

TEXT_IMPORT_MODEL = "text-import"
GROUNDING_THRESHOLD = 0.75
_TIMECODE_RE = re.compile(r"^\s*\[?((?:\d{1,2}:)?\d{1,2}:\d{2})(?:[.,]\d+)?\]?\s*[-–—:]?\s*")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


def format_timecode(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def _parse_timecode(value: str) -> float:
    parts = [int(part) for part in value.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    hours, minutes, secs = parts
    return float(hours * 3600 + minutes * 60 + secs)


def transcription_from_text(text: str, source: str) -> MeetingTranscription:
    """Готовая стенограмма (TXT/DOCX/PDF) -> сегменты; таймкоды берутся из строк вида [00:12:30]."""
    segments: list[TranscriptionSegment] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        start = segments[-1].end if segments else 0.0
        match = _TIMECODE_RE.match(line)
        if match:
            start = _parse_timecode(match.group(1))
            line = line[match.end() :].strip()
        for sentence in _SENTENCE_SPLIT_RE.split(line):
            sentence = sentence.strip()
            if sentence:
                segments.append(TranscriptionSegment(start=start, end=start, text=sentence))
    full_text = " ".join(segment.text for segment in segments)
    return MeetingTranscription(
        model=TEXT_IMPORT_MODEL, source=source, text=full_text, segments=segments
    )


def load_transcript_file(path: Path, original_name: str) -> MeetingTranscription:
    """JSON в формате MeetingTranscription (вывод GigaAM) либо текстовая стенограмма."""
    if path.suffix.casefold() == ".json":
        try:
            return MeetingTranscription.model_validate_json(path.read_text(encoding="utf-8-sig"))
        except (ValidationError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise DocumentParseError(
                "JSON-стенограмма должна соответствовать формату MeetingTranscription "
                "(поля model, source, text, segments)"
            ) from exc
    transcription = transcription_from_text(extract_text(path), original_name)
    if not transcription.segments:
        raise DocumentParseError(f"Стенограмма «{original_name}» не содержит текста")
    return transcription


def ensure_segments(transcription: MeetingTranscription) -> MeetingTranscription:
    if transcription.segments or not transcription.text.strip():
        return transcription
    rebuilt = transcription_from_text(transcription.text, transcription.source)
    return transcription.model_copy(update={"segments": rebuilt.segments})


@dataclass(frozen=True)
class TranscriptChunk:
    index: int
    segment_ids: list[int]
    text: str

    @property
    def first_segment(self) -> int:
        return self.segment_ids[0]

    @property
    def last_segment(self) -> int:
        return self.segment_ids[-1]


def format_segment(segment_id: int, segment: TranscriptionSegment) -> str:
    return f"[{segment_id} | {format_timecode(segment.start)}] {segment.text.strip()}"


def chunk_transcript(
    transcription: MeetingTranscription, max_chars: int, overlap_segments: int
) -> list[TranscriptChunk]:
    """Нарезка по границам сегментов с перекрытием, чтобы поручение не разрезалось."""
    lines = [format_segment(index, seg) for index, seg in enumerate(transcription.segments)]
    chunks: list[TranscriptChunk] = []
    start = 0
    while start < len(lines):
        end = start
        size = 0
        while end < len(lines) and (end == start or size + len(lines[end]) + 1 <= max_chars):
            size += len(lines[end]) + 1
            end += 1
        ids = list(range(start, end))
        chunks.append(
            TranscriptChunk(index=len(chunks), segment_ids=ids, text="\n".join(lines[start:end]))
        )
        if end >= len(lines):
            break
        start = max(end - overlap_segments, start + 1)
    return chunks


@dataclass(frozen=True)
class GroundingResult:
    grounded: bool
    score: float
    segment_ids: list[int] = field(default_factory=list)
    start: float | None = None
    end: float | None = None

    def window_text(self, index: "TranscriptIndex", padding: int = 1) -> str:
        return index.window_text(self.segment_ids, padding)


class TranscriptIndex:
    def __init__(self, transcription: MeetingTranscription) -> None:
        self.transcription = transcription
        self.segments = transcription.segments
        self._stem_sets = [set(stems(segment.text)) for segment in self.segments]

    def window_text(self, segment_ids: list[int], padding: int = 1) -> str:
        if not segment_ids:
            return ""
        first = max(0, min(segment_ids) - padding)
        last = min(len(self.segments) - 1, max(segment_ids) + padding)
        return " ".join(segment.text for segment in self.segments[first : last + 1])

    def _window_stems(self, first: int, width: int) -> set[str]:
        result: set[str] = set()
        for index in range(first, min(first + width, len(self.segments))):
            result |= self._stem_sets[index]
        return result

    def _result(self, segment_ids: list[int], score: float) -> GroundingResult:
        return GroundingResult(
            grounded=True,
            score=score,
            segment_ids=segment_ids,
            start=self.segments[segment_ids[0]].start,
            end=self.segments[segment_ids[-1]].end,
        )

    def _best_window(self, quote: str, candidates: list[int]) -> tuple[float, list[int]]:
        best_score = 0.0
        best_ids: list[int] = []
        for width in (1, 2, 3, 4):
            for first in candidates:
                ids = list(range(first, min(first + width, len(self.segments))))
                if len(ids) < width and width > 1:
                    continue
                text = " ".join(self.segments[i].text for i in ids)
                score = ordered_support(quote, text)
                if score > best_score + 1e-9:
                    best_score, best_ids = score, ids
            if best_score >= 0.999:
                break
        return best_score, best_ids

    def locate(
        self, quote: str | None, hint_segment_ids: list[int] | None = None
    ) -> GroundingResult:
        """Ищет цитату сначала рядом с указанными LLM сегментами, затем по всей стенограмме."""
        if not quote or not self.segments:
            return GroundingResult(grounded=False, score=0.0)
        quote_stems = stems(quote, drop_stop_words=False)
        threshold = GROUNDING_THRESHOLD if len(quote_stems) >= 3 else 0.999

        valid_hints = sorted({i for i in hint_segment_ids or [] if 0 <= i < len(self.segments)})
        if valid_hints:
            nearby = sorted(
                {
                    j
                    for i in valid_hints
                    for j in range(max(0, i - 3), min(len(self.segments), i + 2))
                }
            )
            score, ids = self._best_window(quote, nearby)
            if score >= threshold:
                return self._result(ids, score)

        significant = set(stems(quote))
        if not significant:
            return GroundingResult(grounded=False, score=0.0)
        required = max(1, int(len(significant) * 0.5))
        candidates = [
            index
            for index in range(len(self.segments))
            if len(significant & self._window_stems(index, 4)) >= required
        ]
        score, ids = self._best_window(quote, candidates)
        if score >= threshold:
            return self._result(ids, score)
        return GroundingResult(grounded=False, score=score)

    def mention_supported(self, mention: str | None, context: str) -> bool:
        """Упоминание (ФИО, срок) действительно есть в цитате/окне стенограммы."""
        if not mention:
            return False
        return contains_all_stems(mention, context)

    def contains(self, phrase: str) -> bool:
        return any(contains_all_stems(phrase, segment.text) for segment in self.segments)

    def search(self, query: str, top_k: int = 8) -> list[int]:
        """Лексический поиск сегментов, релевантных запросу (для контекста ИИ-правок)."""
        query_stems = set(stems(query))
        if not query_stems:
            return []
        scored = [
            (len(stem_set & query_stems), index)
            for index, stem_set in enumerate(self._stem_sets)
            if stem_set & query_stems
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return sorted(index for _, index in scored[:top_k])
