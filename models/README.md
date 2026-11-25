# Модели

Здесь лежат GGUF-файлы для локального распознавания задач (Gemma 4 E2B):

- `gemma/gemma-4-E2B-it-UD-Q4_K_XL.gguf` — основная мультимодальная модель;
- `gemma/mmproj-F16.gguf` — мультимодальный проектор (изображения);
- `gemma/mtp-gemma-4-E2B-it.gguf` — MTP-драфтер для спекулятивного
  декодирования (ускоряет генерацию).

Сами файлы в git не хранятся (это ~4.3 ГБ, GitHub не принимает файлы
больше 100 МБ). Их скачивает скрипт:

```bash
make models
```

Скрипт `scripts/download-models.sh` берёт файлы из публичного репозитория
[`unsloth/gemma-4-E2B-it-GGUF`](https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF)
на закреплённой ревизии и сверяет SHA256 с `scripts/models.lock`.
Поэтому на всех компьютерах будут одинаковые файлы.

`make compose-up` вызывает `make models` автоматически.

Старые файлы Qwen в корне `models/` (`Qwen3.5-4B-UD-Q4_K_XL.gguf` и
`mmproj-F16.gguf`) больше не используются — их можно удалить, чтобы
освободить ~3.6 ГБ.
