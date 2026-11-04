#!/usr/bin/env bash
#
# Автоопределение железа и подбор настроек для llama-server.
#
# Использование:
#   ./scripts/detect-gpu.sh        # показать рекомендации
#   ./scripts/detect-gpu.sh --apply # записать в .env
#
# Что определяет:
#   - наличие NVIDIA GPU (nvidia-smi) и объём VRAM
#   - доступность CPU-only fallback
#   - запуск внутри Docker или на хосте
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-.env}"
APPLY=0
if [[ "${1:-}" == "--apply" ]]; then
  APPLY=1
fi

# ---------- helpers ----------

have() { command -v "$1" >/dev/null 2>&1; }

info()  { printf '\033[1;36m[INFO]\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m[OK]\033[0m  %s\n' "$*"; }
err()   { printf '\033[1;31m[ERR]\033[0m %s\n' "$*" >&2; }

# Чтение значения из .env (возвращает пустую строку, если нет)
env_get() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true
}

# Запись/замена значения в .env. Если ключа нет — добавляет в конец.
env_set() {
  local key="$1" value="$2"
  if grep -qE "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s#^${key}=.*#${key}=${value}#" "$ENV_FILE"
  else
    echo "${key}=${value}" >> "$ENV_FILE"
  fi
}

# ---------- detection ----------

IN_DOCKER=0
if [[ -f /.dockerenv ]] || grep -qa docker /proc/1/cgroup 2>/dev/null; then
  IN_DOCKER=1
fi

HAVE_NVIDIA_SMI=0
GPU_NAME=""
VRAM_MB=0
if have nvidia-smi; then
  HAVE_NVIDIA_SMI=1
  GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 | xargs || true)"
  VRAM_MB="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | xargs || true)"
  VRAM_MB="${VRAM_MB:-0}"
fi

HAVE_LLAMA_SERVER=0
if have llama-server; then
  HAVE_LLAMA_SERVER=1
fi

# ---------- подбор настроек ----------

# Базовые значения (CPU-only, безопасные для любого железа)
GPU_LAYERS=0
MMPROJ_OFFLOAD="false"
CTX_SIZE="8192"
MODEL_FILE="Qwen3.5-4B-UD-Q4_K_XL.gguf"
REASON="CPU-only (нет NVIDIA GPU или nvidia-smi недоступен)"

if [[ $HAVE_NVIDIA_SMI -eq 1 && $VRAM_MB -gt 0 ]]; then
  VRAM_GB=$(( VRAM_MB / 1024 ))

  if [[ $VRAM_GB -ge 24 ]]; then
    GPU_LAYERS=99
    MMPROJ_OFFLOAD="true"
    CTX_SIZE="32768"
    MODEL_FILE="Qwen3.5-4B-UD-Q6_K.gguf"
    REASON="24+ ГБ VRAM — полный оффлоад модели и проектора, большой контекст"
  elif [[ $VRAM_GB -ge 16 ]]; then
    GPU_LAYERS=99
    MMPROJ_OFFLOAD="true"
    CTX_SIZE="16384"
    MODEL_FILE="Qwen3.5-4B-UD-Q5_K_M.gguf"
    REASON="16+ ГБ VRAM — полный оффлоад модели и проектора, контекст 16К"
  elif [[ $VRAM_GB -ge 12 ]]; then
    GPU_LAYERS=35
    MMPROJ_OFFLOAD="true"
    CTX_SIZE="16384"
    MODEL_FILE="Qwen3.5-4B-UD-Q4_K_XL.gguf"
    REASON="12+ ГБ VRAM — модель и проектор на GPU, контекст 16К"
  elif [[ $VRAM_GB -ge 8 ]]; then
    GPU_LAYERS=28
    MMPROJ_OFFLOAD="true"
    CTX_SIZE="12288"
    MODEL_FILE="Qwen3.5-4B-UD-Q4_K_XL.gguf"
    REASON="8+ ГБ VRAM — большая часть слоёв на GPU, контекст 12К"
  elif [[ $VRAM_GB -ge 6 ]]; then
    GPU_LAYERS=20
    MMPROJ_OFFLOAD="false"
    CTX_SIZE="8192"
    MODEL_FILE="Qwen3.5-4B-UD-Q4_K_XL.gguf"
    REASON="6 ГБ VRAM — порядка 20 слоёв на GPU, проектор на CPU, контекст 8К"
  elif [[ $VRAM_GB -ge 4 ]]; then
    GPU_LAYERS=14
    MMPROJ_OFFLOAD="false"
    CTX_SIZE="8192"
    MODEL_FILE="Qwen3.5-4B-UD-Q4_K_M.gguf"
    REASON="4 ГБ VRAM — ~14 слоёв на GPU, более компактная квантовка Q4_K_M, контекст 8К"
  else
    GPU_LAYERS=0
    MMPROJ_OFFLOAD="false"
    CTX_SIZE="4096"
    MODEL_FILE="Qwen3.5-4B-UD-Q4_K_S.gguf"
    REASON="Менее 4 ГБ VRAM — только CPU, маленькая квантовка Q4_K_S, контекст 4К"
  fi
fi

# ---------- вывод ----------

echo "=============================================="
echo "  Автоопределение настроек llama-server"
echo "=============================================="
echo "Рабочая директория: $ROOT_DIR"
echo "Файл окружения:     $ENV_FILE"
echo "Внутри Docker:      $([[ $IN_DOCKER -eq 1 ]] && echo "да" || echo "нет")"
echo "nvidia-smi:         $([[ $HAVE_NVIDIA_SMI -eq 1 ]] && echo "да ($GPU_NAME, ${VRAM_MB} МБ)" || echo "нет")"
echo "llama-server:       $([[ $HAVE_LLAMA_SERVER -eq 1 ]] && echo "да в PATH" || echo "нет в PATH")"
echo ""
echo "Обнаруженное VRAM: ${VRAM_GB:-0} ГБ"
echo "Рекомендация: $REASON"
echo ""
echo "Параметры:"
echo "  LOCAL_LLM_GPU_LAYERS=$GPU_LAYERS"
echo "  LOCAL_LLM_MMPROJ_OFFLOAD=$MMPROJ_OFFLOAD"
echo "  LOCAL_LLM_CTX_SIZE=$CTX_SIZE"
echo "  LOCAL_LLM_MODEL_FILE=$MODEL_FILE"
echo ""

if [[ $APPLY -eq 1 ]]; then
  env_set LOCAL_LLM_GPU_LAYERS "$GPU_LAYERS"
  env_set LOCAL_LLM_MMPROJ_OFFLOAD "$MMPROJ_OFFLOAD"
  env_set LOCAL_LLM_CTX_SIZE "$CTX_SIZE"
  env_set LOCAL_LLM_MODEL_FILE "$MODEL_FILE"
  echo "Записано в $ENV_FILE"
else
  echo "Чтобы применить, запустите: ./scripts/detect-gpu.sh --apply"
fi
