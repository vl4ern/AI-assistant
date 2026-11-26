#!/usr/bin/env bash
#
# Скачивает GGUF-модель Gemma, мультимодальный проектор и MTP-драфтер
# для llama-server. Файлы кладутся в models/gemma/ и проверяются по SHA256
# из scripts/models.lock.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODEL_DIR="${LOCAL_LLM_MODELS_DIR:-models/gemma}"
MODEL_FILE="${LOCAL_LLM_MODEL_FILE:-gemma-4-E2B-it-UD-Q4_K_XL.gguf}"
MMPROJ_FILE="${LOCAL_LLM_MMPROJ_FILE:-mmproj-F16.gguf}"
MTP_FILE="${LOCAL_LLM_MTP_FILE:-mtp-gemma-4-E2B-it.gguf}"
HF_REPO="${LOCAL_LLM_HF_REPO:-unsloth/gemma-4-E2B-it-GGUF}"
HF_REVISION="${LOCAL_LLM_HF_REVISION:-0314792d7f1f7e229411f620751375812bb9faf2}"
BASE_URL="https://huggingface.co/${HF_REPO}/resolve/${HF_REVISION}"
LOCK_FILE="${LOCAL_LLM_MODELS_LOCK:-scripts/models.lock}"

if ! command -v curl >/dev/null 2>&1; then
  echo "Ошибка: нужен curl, чтобы скачать модели." >&2
  exit 1
fi

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    echo "Ошибка: не найден sha256sum или shasum." >&2
    return 1
  fi
}

expected_sha() {
  if [[ ! -f "$LOCK_FILE" ]]; then
    echo ""
    return 0
  fi
  awk -F '\t' -v file="$1" '$1 == file {print $2; exit}' "$LOCK_FILE"
}

download_one() {
  local file="$1"
  local dest="$MODEL_DIR/$file"
  local expected
  local actual
  expected="$(expected_sha "$file")"

  if [[ -f "$dest" ]]; then
    if [[ -n "$expected" ]]; then
      echo "Проверяю $dest ..."
      actual="$(sha256_file "$dest")"
      if [[ "$actual" == "$expected" ]]; then
        echo "OK: $dest"
        return 0
      fi
      echo "SHA256 не совпала — перекачиваю $file" >&2
    else
      echo "Уже есть: $dest"
      return 0
    fi
  fi

  echo "Скачиваю $file из $HF_REPO ..."
  if ! curl -fL --retry 5 --retry-delay 3 -C - \
    -o "$dest.part" "$BASE_URL/$file"; then
    echo "Докачка не удалась, пробую заново с нуля..." >&2
    rm -f "$dest.part"
    curl -fL --retry 5 --retry-delay 3 -o "$dest.part" "$BASE_URL/$file"
  fi
  mv "$dest.part" "$dest"

  if [[ -n "$expected" ]]; then
    actual="$(sha256_file "$dest")"
    if [[ "$actual" != "$expected" ]]; then
      echo "Ошибка: SHA256 файла $file не совпала с models.lock." >&2
      echo "Ожидалось: $expected" >&2
      echo "Получено:  $actual" >&2
      rm -f "$dest"
      exit 1
    fi
  fi
  echo "Готово: $dest"
}

mkdir -p "$MODEL_DIR"
download_one "$MODEL_FILE"
if [[ -n "$MMPROJ_FILE" ]]; then
  download_one "$MMPROJ_FILE"
fi
if [[ -n "$MTP_FILE" ]]; then
  download_one "$MTP_FILE"
fi

echo "Модели готовы: $MODEL_DIR"
