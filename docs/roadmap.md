# Roadmap (предложение на 5 этапов)

## Этап 0. Базовый каркас (сделано)

- [x] Монорепо-структура.
- [x] API + frontend-заглушка.
- [x] Документация по ролям и workflow.

## Этап 1. MVP ядро

- Intelligence: стабильный greedy scheduler + dependency handling.
- Knowledge: переход с in-memory на PostgreSQL и миграции.
- Integrations: один рабочий импорт (например, Google Calendar import).
- Frontend: Today + Task list + создание задач.

## Этап 2. Полезность для студентов

- Intelligence: окна между парами, учет времени бодрствования.
- Knowledge: task history, фактическое время выполнения.
- Integrations: LMS импорт расписания.
- Frontend: Calendar week-view + prime-task блок.

## Этап 3. Аналитика

- Метрики: % on-time, overload index, estimate error.
- Рекомендации по перераспределению нагрузки.
- Analytics dashboard на frontend.

## Этап 4. Предзащита

- Полный сценарий: импорт -> планирование -> выполнение -> аналитика.
- Тесты ключевых сценариев.
- Финальная полировка UX и презентации.
