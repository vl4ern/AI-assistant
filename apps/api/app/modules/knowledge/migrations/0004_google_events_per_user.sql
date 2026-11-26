-- Раньше импортированные события Google сохранялись с user_id = 'shared'
-- и были видны во всех аккаунтах. Удаляем их: следующий импорт создаст
-- события уже с владельцем (см. передачу user_id в kb_bridge).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM schema_migrations WHERE name = '0004_google_events_per_user'
    ) THEN
        DELETE FROM events
        WHERE source = 'google-calendar' AND user_id = 'shared';

        INSERT INTO schema_migrations(name) VALUES ('0004_google_events_per_user');
    END IF;
END $$;
