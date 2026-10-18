#!/usr/bin/env bash
set -euo pipefail

# Значения по умолчанию
CONTEXT_SIZE="${1:-4096}"
GPU_LAYERS="${2:-0}"
PORT="${3:-8080}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

MODEL_PATH="${PROJECT_ROOT}/models/gigachat/GigaChat3.1-10B-A1.8B-q4_K_M.gguf"
SERVER_PATH="${PROJECT_ROOT}/tools/llama.cpp/llama-server"

# Fallback на системный llama-server, если локальный бинарник не установлен в tools/
if [[ ! -f "$SERVER_PATH" ]]; then
    if command -v llama-server &>/dev/null; then
        SERVER_PATH="$(command -v llama-server)"
    else
        echo "Ошибка: llama-server не найден ни по пути '$SERVER_PATH', ни в PATH." >&2
        echo "Установите llama.cpp или соберите сервер." >&2
        exit 1
    fi
fi

if [[ ! -f "$MODEL_PATH" ]]; then
    echo "Ошибка: Модель не найдена: $MODEL_PATH" >&2
    echo "Сначала запустите: python scripts/download_gigachat.py" >&2
    exit 1
fi

echo "Запуск локального сервера GigaChat на http://127.0.0.1:${PORT}..."
exec "$SERVER_PATH" \
    --model "$MODEL_PATH" \
    --host "127.0.0.1" \
    --port "$PORT" \
    --ctx-size "$CONTEXT_SIZE" \
    --n-gpu-layers "$GPU_LAYERS" \
    --jinja \
    -np 1
