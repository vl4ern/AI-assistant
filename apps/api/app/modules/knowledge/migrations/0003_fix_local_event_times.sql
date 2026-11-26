-- Исторические данные: naive-время локального пояса (Минск, UTC+3) было
-- записано в TIMESTAMPTZ как UTC. Из-за этого события в интерфейсе и пары,
-- экспортированные в Google, уезжали на +3 часа. Сдвигаем один раз.
CREATE TABLE IF NOT EXISTS schema_migrations (
    name TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM schema_migrations WHERE name = '0003_fix_local_event_times'
    ) THEN
        UPDATE events
        SET start_at = start_at - INTERVAL '3 hours',
            end_at = end_at - INTERVAL '3 hours'
        WHERE source IN ('bsuir-lms', 'google-calendar');

        -- Слоты планировщика тоже строились из naive-времени.
        UPDATE tasks
        SET scheduled_start = scheduled_start - INTERVAL '3 hours',
            scheduled_end = scheduled_end - INTERVAL '3 hours'
        WHERE scheduled_start IS NOT NULL;

        INSERT INTO schema_migrations(name) VALUES ('0003_fix_local_event_times');
    END IF;
END $$;
