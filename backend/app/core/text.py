"""Лёгкие текстовые утилиты для русского языка без внешних NLP-зависимостей.

Используются для сверки цитат со стенограммой, поиска похожих поручений
и сопоставления ФИО. Стемминг грубый (отсечение окончаний + усечение),
но детерминированный и достаточный для лексического сравнения.
"""

import re
from difflib import SequenceMatcher

_WORD_RE = re.compile(r"[0-9a-zа-яё]+", re.IGNORECASE)

STOP_WORDS = frozenset(
    {
        "а", "в", "во", "и", "к", "ко", "на", "по", "с", "со", "о", "об", "от", "до", "для",
        "за", "из", "не", "ни", "что", "это", "но", "же", "ли", "бы", "то", "как", "также",
        "все", "всем", "его", "ее", "их", "у", "при", "так", "или", "мы", "вы", "он", "она",
        "они", "нам", "вам", "был", "была", "были", "будет", "есть", "уже", "еще",
    }
)  # fmt: skip

_ENDINGS = sorted(
    [
        "иями", "ями", "ами", "ого", "его", "ому", "ему", "ыми", "ими", "иях", "ость",
        "ах", "ях", "ов", "ев", "ой", "ей", "ий", "ый", "ая", "яя", "ое", "ее", "ые", "ие",
        "ом", "ем", "ам", "ям", "ую", "юю", "ым", "им", "ть", "а", "я", "о", "е", "ы", "и",
        "у", "ю", "й", "ь",
    ],
    key=len,
    reverse=True,
)  # fmt: skip
_STEM_LENGTH = 6


def normalize_text(text: str) -> str:
    """Нижний регистр, ё -> е, схлопывание пробелов."""
    return " ".join(text.casefold().replace("ё", "е").split())


def tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(normalize_text(text))


def stem(word: str) -> str:
    word = normalize_text(word)
    if len(word) <= 3:
        return word
    for ending in _ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            word = word[: -len(ending)]
            break
    return word[:_STEM_LENGTH]


def stems(text: str, drop_stop_words: bool = True) -> list[str]:
    return [
        stem(token) for token in tokenize(text) if not (drop_stop_words and token in STOP_WORDS)
    ]


def similarity(left: str, right: str) -> float:
    """Коэффициент Жаккара по множествам основ (0..1)."""
    left_set = set(stems(left))
    right_set = set(stems(right))
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def ordered_support(needle: str, haystack: str) -> float:
    """Доля основ `needle`, встречающихся в `haystack` в том же порядке (0..1).

    Применяется для проверки, что цитата действительно взята из стенограммы,
    допуская мелкие расхождения словоформ и пунктуации.
    """
    needle_stems = stems(needle, drop_stop_words=False)
    if not needle_stems:
        return 0.0
    haystack_stems = stems(haystack, drop_stop_words=False)
    if not haystack_stems:
        return 0.0
    matcher = SequenceMatcher(None, needle_stems, haystack_stems, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return matched / len(needle_stems)


def contains_all_stems(needle: str, haystack: str) -> bool:
    """Все значимые слова `needle` присутствуют в `haystack` (с учётом словоформ)."""
    needle_set = set(stems(needle, drop_stop_words=False))
    if not needle_set:
        return False
    return needle_set <= set(stems(haystack, drop_stop_words=False))


_NAME_WORD = r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?"
FULL_NAME_RE = re.compile(
    rf"\b({_NAME_WORD})\s+({_NAME_WORD})\s+([А-ЯЁ][а-яё]+(?:ич|на|оглы|кызы))\b"
)
SURNAME_INITIALS_RE = re.compile(rf"\b({_NAME_WORD})\s*([А-ЯЁ])\.\s*([А-ЯЁ])\.?")
INITIALS_SURNAME_RE = re.compile(rf"\b([А-ЯЁ])\.\s*([А-ЯЁ])\.\s*({_NAME_WORD})\b")


def short_name(full_name: str) -> str:
    """«Иванов Иван Иванович» / «И.И. Иванов» -> «Иванов И.И.»; иначе строка без изменений."""
    text = " ".join(full_name.split())
    full = FULL_NAME_RE.fullmatch(text)
    if full:
        surname, name, patronymic = full.groups()
        return f"{surname} {name[0]}.{patronymic[0]}."
    initials_after = SURNAME_INITIALS_RE.fullmatch(text)
    if initials_after:
        surname, first, second = initials_after.groups()
        return f"{surname} {first}.{second}."
    initials_before = INITIALS_SURNAME_RE.fullmatch(text)
    if initials_before:
        first, second, surname = initials_before.groups()
        return f"{surname} {first}.{second}."
    return text


def find_person_name(text: str) -> tuple[str, int, int] | None:
    """Первое ФИО в строке: (найденный текст, начало, конец)."""
    candidates = [
        match
        for pattern in (FULL_NAME_RE, SURNAME_INITIALS_RE, INITIALS_SURNAME_RE)
        if (match := pattern.search(text)) is not None
    ]
    if not candidates:
        return None
    best = min(candidates, key=lambda match: (match.start(), -len(match.group(0))))
    return best.group(0).strip(), best.start(), best.end()
