import pytest

from backend.app.schemas.transcription import DomainVocabulary
from backend.app.services.domain_vocabulary import (
    DomainTextNormalizer,
    build_domain_context,
)


def test_vocabulary_removes_duplicates_and_empty_entries():
    vocabulary = DomainVocabulary(
        people=[" Иванов   Иван ", "иванов иван", "Петрова Анна", " "],
        abbreviations=["ЕГЭ", "егэ", "ОГЭ"],
    )

    assert vocabulary.people == ["Иванов Иван", "Петрова Анна"]
    assert vocabulary.abbreviations == ["ЕГЭ", "ОГЭ"]


def test_empty_vocabulary_does_not_change_text():
    vocabulary = DomainVocabulary()
    text = "Егэ, неизвестная организация и любые слова остаются как есть."

    assert build_domain_context(vocabulary) == ""
    assert DomainTextNormalizer(vocabulary).normalize(text) == text


def test_context_contains_all_categories_in_stable_order():
    vocabulary = DomainVocabulary(
        people=["Иванов Иван Иванович"],
        positions=["Министр образования"],
        organizations=["Министерство образования Свердловской области"],
        abbreviations=["ЕГЭ"],
        terms=["Федеральный проект"],
    )

    expected = (
        "Иванов Иван Иванович; Министр образования; "
        "Министерство образования Свердловской области; ЕГЭ; Федеральный проект"
    )
    assert build_domain_context(vocabulary) == expected
    assert build_domain_context(vocabulary) == expected


def test_context_deduplicates_entries_across_categories():
    vocabulary = DomainVocabulary(people=["ИРО"], abbreviations=["ИРО", "ЕГЭ"])

    assert build_domain_context(vocabulary) == "ИРО; ЕГЭ"


def test_context_respects_size_limit_without_cutting_entries():
    vocabulary = DomainVocabulary(people=["СлишкомДлинноеИмя"], abbreviations=["ЕГЭ", "ИРО"])

    context = build_domain_context(vocabulary, max_chars=8)

    assert context == "ЕГЭ; ИРО"
    assert len(context) <= 8
    assert build_domain_context(vocabulary, max_chars=0) == ""
    with pytest.raises(ValueError, match="max_chars"):
        build_domain_context(vocabulary, max_chars=-1)


def test_postprocessing_normalizes_known_abbreviations_only():
    normalizer = DomainTextNormalizer(DomainVocabulary(abbreviations=["ЕГЭ", "ОГЭ"]))

    assert normalizer.normalize("Егэ и огэ, но ЕГЭПО") == "ЕГЭ и ОГЭ, но ЕГЭПО"


def test_postprocessing_does_not_replace_unknown_or_similar_words():
    normalizer = DomainTextNormalizer(
        DomainVocabulary(abbreviations=["ЕГЭ"], terms=["Профессионалитет"])
    )
    text = "ОГЭ, ЕГЭПО, профессиональность и неизвестный термин."

    assert normalizer.normalize(text) == text


def test_postprocessing_normalizes_safe_organization_variants():
    organization = "ГАОУ ДПО Свердловской области «ИРО»"
    normalizer = DomainTextNormalizer(DomainVocabulary(organizations=[organization]))

    assert normalizer.normalize('гаоу   дпо свердловской области "иро"') == organization


def test_postprocessing_normalizes_unambiguous_person_name_order():
    normalizer = DomainTextNormalizer(DomainVocabulary(people=["Иванов Иван Иванович"]))

    assert (
        normalizer.normalize("Доклад подготовил иван иванович иванов.")
        == "Доклад подготовил Иванов Иван Иванович."
    )


def test_postprocessing_skips_ambiguous_person_name_matches():
    normalizer = DomainTextNormalizer(
        DomainVocabulary(people=["Иванов Иван Иванович", "Иван Иванович Иванов"])
    )
    text = "Слово предоставлено ивану ивановичу иванову и Иван Иванович Иванов."

    assert normalizer.normalize(text) == text
