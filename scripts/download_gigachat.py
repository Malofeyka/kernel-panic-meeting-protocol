import argparse
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import hf_hub_download

load_dotenv()

REPO_ID = "ai-sage/GigaChat3.1-10B-A1.8B-GGUF"
REVISION = "97045b260251cfa86f5ad25638fa2dd074153446"
FILENAME = "GigaChat3.1-10B-A1.8B-q4_K_M.gguf"
EXPECTED_SIZE = 6_474_702_976
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Скачивание локальной модели GigaChat GGUF")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "models" / "gigachat",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model_path = args.output_dir / FILENAME
    if not (model_path.is_file() and model_path.stat().st_size == EXPECTED_SIZE):
        model_path = Path(
            hf_hub_download(
                repo_id=REPO_ID,
                filename=FILENAME,
                revision=REVISION,
                local_dir=args.output_dir,
            )
        )
    actual_size = model_path.stat().st_size
    if actual_size != EXPECTED_SIZE:
        raise RuntimeError(
            f"Неверный размер модели: ожидалось {EXPECTED_SIZE}, получено {actual_size} байт"
        )
    print(f"Модель сохранена: {model_path} ({actual_size} байт)")


if __name__ == "__main__":
    main()
