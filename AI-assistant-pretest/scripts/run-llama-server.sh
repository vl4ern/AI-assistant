#!/usr/bin/env bash
#
# Локальный запуск мультимодальной модели (без Docker).
# Для Docker-запуска используйте `make compose-up`: там llama-server
# поднимается отдельным контейнером.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-llama-server}"
MODEL_FILE="${LOCAL_LLM_MODEL_FILE:-Qwen3.5-4B-UD-Q4_K_XL.gguf}"
MMPROJ_FILE="${LOCAL_LLM_MMPROJ_FILE:-mmproj-F16.gguf}"
MODEL_PATH="${LOCAL_LLM_MODEL_PATH:-models/$MODEL_FILE}"
MMPROJ_PATH="${LOCAL_LLM_MMPROJ_PATH:-models/$MMPROJ_FILE}"
HOST="${LOCAL_LLM_HOST:-0.0.0.0}"
PORT="${LOCAL_LLM_PORT:-8080}"
CTX_SIZE="${LOCAL_LLM_CTX_SIZE:-16384}"
ALIAS="${LOCAL_LLM_MODEL:-qwen3.5-4b}"
IMAGE_MIN_TOKENS="${LOCAL_LLM_IMAGE_MIN_TOKENS:-1024}"

# Автоподбор количества GPU-слоёв, если не задан явно.
if [[ -z "${LOCAL_LLM_GPU_LAYERS:-}" ]]; then
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
    VRAM_MB="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | xargs || echo 0)"
    VRAM_MB="${VRAM_MB:-0}"
    VRAM_GB=$(( VRAM_MB / 1024 ))
    if [[ $VRAM_GB -ge 16 ]]; then
      GPU_LAYERS=99
    elif [[ $VRAM_GB -ge 12 ]]; then
      GPU_LAYERS=35
    elif [[ $VRAM_GB -ge 8 ]]; then
      GPU_LAYERS=28
    elif [[ $VRAM_GB -ge 6 ]]; then
      GPU_LAYERS=20
    elif [[ $VRAM_GB -ge 4 ]]; then
      GPU_LAYERS=14
    else
      GPU_LAYERS=0
    fi
    echo "Автоподбор GPU-слоёв: $GPU_LAYERS (VRAM ${VRAM_GB} ГБ)"
  else
    GPU_LAYERS=0
    echo "NVIDIA GPU не найдена — запуск на CPU (GPU-слоёв: 0)"
  fi
else
  GPU_LAYERS="${LOCAL_LLM_GPU_LAYERS}"
fi

if [[ "$LLAMA_SERVER_BIN" == */* ]]; then
  if [[ ! -x "$LLAMA_SERVER_BIN" ]]; then
    echo "Ошибка: llama-server не найден или не исполняемый: $LLAMA_SERVER_BIN" >&2
    echo "Укажите путь: LLAMA_SERVER_BIN=/path/to/llama-server make llm-dev" >&2
    exit 1
  fi
elif ! command -v "$LLAMA_SERVER_BIN" >/dev/null 2>&1; then
  echo "Ошибка: команда '$LLAMA_SERVER_BIN' не найдена в PATH." >&2
  echo "Укажите путь: LLAMA_SERVER_BIN=/path/to/llama-server make llm-dev" >&2
  exit 1
fi

if [[ ! -f "$MODEL_PATH" ]]; then
  echo "Ошибка: модель не найдена: $MODEL_PATH" >&2
  echo "Скачайте модели: make models" >&2
  exit 1
fi

ARGS=(
  --model "$MODEL_PATH"
  --host "$HOST"
  --port "$PORT"
  --ctx-size "$CTX_SIZE"
  --n-gpu-layers "$GPU_LAYERS"
  --image-min-tokens "$IMAGE_MIN_TOKENS"
  --alias "$ALIAS"
  --jinja
)

if [[ -f "$MMPROJ_PATH" ]]; then
  ARGS+=(--mmproj "$MMPROJ_PATH")
else
  echo "Внимание: mmproj не найден ($MMPROJ_PATH) — изображения не будут распознаваться." >&2
  echo "Скачайте модели: make models" >&2
fi

echo "llama-server слушает ${HOST}:${PORT} (модель: $ALIAS, GPU-слоёв: $GPU_LAYERS)"
exec "$LLAMA_SERVER_BIN" "${ARGS[@]}"
