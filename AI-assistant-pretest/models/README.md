# Модели

Здесь лежат GGUF-файлы для локального распознавания задач:

- `Qwen3.5-4B-UD-Q4_K_XL.gguf`
- `mmproj-F16.gguf`

Сами файлы в git не хранятся (это ~3.4 ГБ, GitHub не принимает файлы
больше 100 МБ). Их скачивает скрипт:

```bash
make models
```

Скрипт `scripts/download-models.sh` берёт файлы из публичного репозитория
[`unsloth/Qwen3.5-4B-GGUF`](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF)
на закреплённой ревизии и сверяет SHA256 с `scripts/models.lock`.
Поэтому на всех компьютерах будут одинаковые файлы.

`make compose-up` вызывает `make models` автоматически.
