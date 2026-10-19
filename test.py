import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from backend.app.schemas.transcription import DomainVocabulary
from backend.app.services.gigaam_transcriber import GigaAMTranscriber
from backend.app.services.gigachat_client import GigaChatClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Локальная транскрибация GigaAM и summary GigaChat"
    )
    parser.add_argument("input", nargs="?", type=Path, default=Path("test2.mp4"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--model", default=os.getenv("GIGAAM_MODEL", "e2e_rnnt"))
    parser.add_argument("--device", default=os.getenv("GIGAAM_DEVICE"))
    parser.add_argument("--batch-size", type=int)
    parser.add_argument(
        "--vocabulary",
        type=Path,
        help="Путь к JSON-файлу доменного словаря",
    )
    parser.add_argument(
        "--min-duration-on",
        type=float,
        default=None,
        help="Мин. длительность речевого сегмента VAD (сек); по умолчанию GIGAAM_MIN_DURATION_ON или 0.0",
    )
    parser.add_argument(
        "--min-duration-off",
        type=float,
        default=None,
        help="Мин. длительность паузы VAD (сек); по умолчанию GIGAAM_MIN_DURATION_OFF или 0.0",
    )
    return parser.parse_args()


def load_vocabulary(path: Path | None) -> DomainVocabulary | None:
    if path is None:
        return None
    try:
        raw_vocabulary = path.read_text(encoding="utf-8")
    except OSError:
        raise SystemExit(f"Не удалось прочитать файл словаря: {path}") from None
    try:
        return DomainVocabulary.model_validate_json(raw_vocabulary)
    except ValidationError:
        raise SystemExit(
            "Файл словаря должен содержать JSON-объект с полями people, positions, "
            "organizations, abbreviations и terms"
        ) from None


def main() -> None:
    load_dotenv()
    hf_token = os.getenv("HF_TOKEN") or os.getenv("hf")
    if hf_token:
        os.environ["HF_TOKEN"] = hf_token

    args = parse_args()
    vocabulary = load_vocabulary(args.vocabulary)
    batch_size = args.batch_size
    if batch_size is None:
        batch_size = int(os.getenv("GIGAAM_BATCH_SIZE", "4"))

    transcriber = GigaAMTranscriber(
        model_name=args.model,
        device=args.device,
        batch_size=batch_size,
        min_duration_on=args.min_duration_on,
        min_duration_off=args.min_duration_off,
    )
    if vocabulary is None:
        result = transcriber.transcribe(args.input)
    else:
        result = transcriber.transcribe(args.input, vocabulary=vocabulary)

    output_path = args.output or args.input.with_suffix(".json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Сохранено в {output_path}; сегментов: {len(result.segments)}")

    gigachat = GigaChatClient()
    try:
        summary = gigachat.summarize(result)
    finally:
        gigachat.close()

    summary_path = args.summary_output or output_path.with_name(f"{output_path.stem}.summary.json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps({"summary": summary}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Краткая суть совещания:\n{summary}")
    print(f"Summary сохранено в {summary_path}")


if __name__ == "__main__":
    main()
