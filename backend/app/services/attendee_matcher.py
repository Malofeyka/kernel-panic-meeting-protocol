"""Сопоставление упоминаний исполнителей в речи со списком участников (EXT-02).

Учитывает падежи фамилий («Петрову», «Ивановой»), обращение по имени-отчеству
(«Сергею Александровичу»), инициалы и совпадение по должности. Если кандидатов
несколько — результат помечается как неоднозначный и не угадывается.
"""

import re
from dataclasses import dataclass, field

from backend.app.core.text import normalize_text, similarity
from backend.app.schemas.protocol import Attendee

_WORD_RE = re.compile(r"[А-ЯЁа-яё]+(?:-[А-ЯЁа-яё]+)?")
_INITIALS_RE = re.compile(r"\b([А-ЯЁ])\.\s*([А-ЯЁ])\.?")
_SOFT_ENDINGS = ("ая", "ий", "ой", "ый", "а", "я", "ь", "й")


def _base(word: str) -> str:
    word = normalize_text(word)
    for ending in _SOFT_ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            return word[: -len(ending)]
    return word


def _word_matches(token: str, word: str) -> bool:
    base = _base(word)
    token_norm = normalize_text(token)
    if len(base) < 3:
        return token_norm == normalize_text(word)
    return token_norm.startswith(base) and len(token_norm) - len(base) <= 4


@dataclass(frozen=True)
class _PersonParts:
    surname: str
    first_name: str | None
    patronymic: str | None
    initials: tuple[str, str] | None


def _split_person(attendee: Attendee) -> _PersonParts:
    words = attendee.full_name.split()
    if len(words) >= 3 and not words[1].endswith("."):
        return _PersonParts(words[0], words[1], words[2], (words[1][0], words[2][0]))
    initials = _INITIALS_RE.search(attendee.short_name)
    surname = attendee.short_name.split()[0] if attendee.short_name else words[0]
    return _PersonParts(
        surname, None, None, (initials.group(1), initials.group(2)) if initials else None
    )


@dataclass(frozen=True)
class AssigneeResolution:
    assignee: str | None
    role: str | None = None
    matched: bool = False
    ambiguous: bool = False
    candidates: list[str] = field(default_factory=list)


class AttendeeMatcher:
    def __init__(self, attendees: list[Attendee]) -> None:
        self._attendees = attendees
        self._parts = [_split_person(attendee) for attendee in attendees]

    @property
    def has_attendees(self) -> bool:
        return bool(self._attendees)

    @property
    def short_names(self) -> set[str]:
        return {attendee.short_name for attendee in self._attendees}

    def _score(self, mention: str, index: int) -> int:
        parts = self._parts[index]
        tokens = _WORD_RE.findall(mention)
        score = 0
        if any(_word_matches(token, parts.surname) for token in tokens):
            score += 3
            mention_initials = _INITIALS_RE.search(mention)
            if mention_initials and parts.initials:
                if (mention_initials.group(1), mention_initials.group(2)) == parts.initials:
                    score += 1
                else:
                    return 0
        if (
            parts.first_name
            and parts.patronymic
            and any(_word_matches(token, parts.first_name) for token in tokens)
            and any(_word_matches(token, parts.patronymic) for token in tokens)
        ):
            score += 4  # имя + отчество специфичнее одной фамилии
        position = self._attendees[index].position
        if score == 0 and position and similarity(mention, position) >= 0.5:
            score += 1
        return score

    def resolve(self, mention: str | None) -> AssigneeResolution:
        if mention is None or not mention.strip():
            return AssigneeResolution(assignee=None)
        cleaned = " ".join(mention.split()).strip(" ,.;:")
        if not self._attendees:
            return AssigneeResolution(assignee=cleaned or None)

        scores = [(self._score(cleaned, index), index) for index in range(len(self._attendees))]
        best = max(score for score, _ in scores)
        if best == 0:
            return AssigneeResolution(assignee=cleaned or None)
        winners = [index for score, index in scores if score == best]
        if len(winners) > 1:
            return AssigneeResolution(
                assignee=None,
                ambiguous=True,
                candidates=[self._attendees[index].short_name for index in winners],
            )
        attendee = self._attendees[winners[0]]
        return AssigneeResolution(
            assignee=attendee.short_name, role=attendee.position, matched=True
        )

    def role_of(self, short_name: str) -> str | None:
        for attendee in self._attendees:
            if attendee.short_name == short_name:
                return attendee.position
        return None

    def mentioned_in(self, short_name: str, text: str) -> bool:
        """Участник упомянут в тексте (фамилия или имя-отчество в любом падеже)."""
        for index, attendee in enumerate(self._attendees):
            if attendee.short_name == short_name:
                return self._score(text, index) >= 3
        return False


def same_person(left: str | None, right: str | None) -> bool:
    """«Сидоровой С.С.» и «Сидорова С.С.» — один человек (с учётом падежа и инициалов)."""
    if not left or not right:
        return False
    left_words, right_words = _WORD_RE.findall(left), _WORD_RE.findall(right)
    if not left_words or not right_words:
        return normalize_text(left) == normalize_text(right)
    left_base, right_base = _base(left_words[0]), _base(right_words[0])
    if not (left_base.startswith(right_base) or right_base.startswith(left_base)):
        return False
    left_initials, right_initials = _INITIALS_RE.search(left), _INITIALS_RE.search(right)
    if left_initials and right_initials:
        return left_initials.groups() == right_initials.groups()
    return True
