"""Выгрузка OpenAPI-контракта в docs/api/openapi.json.

Запуск после любого изменения API:
    uv run python scripts/export_openapi.py

Фронтенд генерирует из файла TypeScript-типы:
    npx openapi-typescript ../docs/api/openapi.json -o src/api/schema.d.ts
Тест tests/test_openapi_contract.py падает, если файл не синхронизирован с кодом.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "docs" / "api" / "openapi.json"


def render_openapi() -> str:
    sys.path.insert(0, str(ROOT))
    from backend.app.main import app

    return json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    OPENAPI_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPENAPI_PATH.write_text(render_openapi(), encoding="utf-8", newline="\n")
    print(f"OpenAPI-контракт сохранён: {OPENAPI_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
