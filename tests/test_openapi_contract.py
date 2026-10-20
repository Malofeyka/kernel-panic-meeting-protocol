"""Контракт Backend <-> Frontend не должен меняться незаметно для фронтенда."""

from scripts.export_openapi import OPENAPI_PATH, render_openapi


def test_committed_openapi_matches_code() -> None:
    assert OPENAPI_PATH.is_file(), "Выполните: uv run python scripts/export_openapi.py"
    committed = OPENAPI_PATH.read_text(encoding="utf-8")
    assert committed == render_openapi(), (
        "API изменён, а docs/api/openapi.json — нет. Выполните "
        "`uv run python scripts/export_openapi.py`, закоммитьте файл и предупредите фронтенд."
    )
