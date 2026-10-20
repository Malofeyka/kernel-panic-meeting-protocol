import re
from collections.abc import Iterator
from itertools import permutations

from backend.app.schemas.transcription import DomainVocabulary

DEFAULT_CONTEXT_MAX_CHARS = 2000
_QUOTES = '«»"“”'
_QUOTE_PATTERN = '[«»"“”]?'
_QUOTE_TRANSLATION = str.maketrans("", "", _QUOTES)


def _iter_entries(vocabulary: DomainVocabulary) -> Iterator[tuple[str, str]]:
    categories = (
        ("people", vocabulary.people),
        ("positions", vocabulary.positions),
        ("organizations", vocabulary.organizations),
        ("abbreviations", vocabulary.abbreviations),
        ("terms", vocabulary.terms),
    )
    for category, entries in categories:
        for entry in entries:
            yield category, entry


def build_domain_context(
    vocabulary: DomainVocabulary, max_chars: int = DEFAULT_CONTEXT_MAX_CHARS
) -> str:
    if max_chars < 0:
        raise ValueError("max_chars должен быть неотрицательным")

    selected: list[str] = []
    seen: set[str] = set()
    context_length = 0
    for _, entry in _iter_entries(vocabulary):
        key = entry.casefold()
        if key in seen:
            continue
        seen.add(key)
        separator_length = 2 if selected else 0
        entry_length = separator_length + len(entry)
        if context_length + entry_length > max_chars:
            continue
        selected.append(entry)
        context_length += entry_length
    return "; ".join(selected)


def _entry_variants(category: str, entry: str) -> Iterator[str]:
    yield entry
    if category != "people":
        return

    words = entry.split()
    if not 2 <= len(words) <= 3:
        return
    for permutation in permutations(words):
        variant = " ".join(permutation)
        if variant != entry:
            yield variant


def _alias_key(variant: str) -> str:
    without_quotes = variant.translate(_QUOTE_TRANSLATION)
    return " ".join(without_quotes.casefold().split())


def _variant_pattern(variant: str) -> str:
    parts: list[str] = []
    for char in variant:
        if char in _QUOTES:
            parts.append(_QUOTE_PATTERN)
        elif char.isspace():
            parts.append(r"[^\S\r\n]+")
        else:
            parts.append(re.escape(char))
    return rf"(?<!\w){''.join(parts)}(?!\w)"


class DomainTextNormalizer:
    def __init__(self, vocabulary: DomainVocabulary) -> None:
        alias_variants: dict[str, str] = {}
        alias_canonicals: dict[str, set[str]] = {}
        for category, entry in _iter_entries(vocabulary):
            for variant in _entry_variants(category, entry):
                key = _alias_key(variant)
                if not key:
                    continue
                alias_variants.setdefault(key, variant)
                alias_canonicals.setdefault(key, set()).add(entry)

        aliases = [
            (alias_variants[key], next(iter(canonicals)))
            for key, canonicals in alias_canonicals.items()
            if len(canonicals) == 1
        ]
        aliases.sort(key=lambda alias: len(alias[0]), reverse=True)

        self._canonical_by_group = {
            f"alias_{index}": canonical for index, (_, canonical) in enumerate(aliases)
        }
        self._pattern: re.Pattern[str] | None = None
        if aliases:
            self._pattern = re.compile(
                "|".join(
                    f"(?P<alias_{index}>{_variant_pattern(variant)})"
                    for index, (variant, _) in enumerate(aliases)
                ),
                re.IGNORECASE,
            )

    def normalize(self, text: str) -> str:
        if self._pattern is None:
            return text

        def replace(match: re.Match[str]) -> str:
            group_name = match.lastgroup
            if group_name is None:
                return match.group(0)
            return self._canonical_by_group[group_name]

        return self._pattern.sub(replace, text)
