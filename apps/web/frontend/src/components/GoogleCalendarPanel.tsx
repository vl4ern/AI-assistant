import { useCallback, useEffect, useState } from 'react';

import {
  clearGoogleCalendar,
  connectGoogle,
  disconnectGoogle,
  exportPlanToGoogle,
  getGoogleStatus,
  importFromGoogle,
} from '../api/integrations';
import type { GoogleCalendarStatus } from '../api/integrations';
import { useSettings } from '../settings';

type GoogleCalendarPanelProps = {
  // Вызывается после импорта/экспорта, чтобы страница перезагрузила данные.
  onChanged: () => void;
};

const POLL_INTERVAL_MS = 2000;
const MAX_POLL_ATTEMPTS = 150; // 5 минут — как таймаут OAuth-сервера на backend

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return 'Unknown error';
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function GoogleCalendarPanel({ onChanged }: GoogleCalendarPanelProps) {
  const { t, locale } = useSettings();
  const [status, setStatus] = useState<GoogleCalendarStatus | null>(null);
  const [busy, setBusy] = useState<
    'connect' | 'import' | 'export' | 'disconnect' | 'clear' | null
  >(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [popupBlocked, setPopupBlocked] = useState(false);

  const loadStatus = useCallback(async () => {
    try {
      const current = await getGoogleStatus();
      setStatus(current);
      if (current.connected) {
        setAuthUrl(null);
        setPopupBlocked(false);
      } else {
        setAuthUrl(current.auth_url);
      }
    } catch (loadError) {
      setError(getErrorMessage(loadError));
    }
  }, []);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  async function run(
    kind: 'connect' | 'import' | 'export' | 'disconnect' | 'clear'
  ) {
    setBusy(kind);
    setMessage('');
    setError('');
    try {
      if (kind === 'connect') {
        // Открываем окно синхронно, пока ещё жив жест пользователя: после
        // await window.open почти наверняка будет заблокирован браузером.
        const popup = window.open('about:blank', '_blank');
        setPopupBlocked(!popup);

        let current = await connectGoogle();
        setStatus(current);
        setAuthUrl(current.auth_url);

        if (current.auth_error) {
          setError(t('google.authFailed', { error: current.auth_error }));
          popup?.close();
          return;
        }

        if (current.auth_url) {
          if (popup && !popup.closed) {
            popup.location.assign(current.auth_url);
            popup.focus();
          } else {
            // Окно заблокировано — внизу покажем кликабельную ссылку.
            setPopupBlocked(true);
          }
        } else if (current.connected) {
          popup?.close();
        }

        // Ждём завершения OAuth в фоне; при успехе обновляем данные сразу.
        for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt++) {
          await wait(POLL_INTERVAL_MS);
          current = await getGoogleStatus();
          setStatus(current);
          if (current.auth_error && !current.connected) {
            setError(t('google.authFailed', { error: current.auth_error }));
            break;
          }
          if (popup && popup.closed && !current.connected) {
            // Окно закрыли, не завершив вход — даём нажать кнопку снова.
            break;
          }
          if (current.connected) {
            setAuthUrl(null);
            setPopupBlocked(false);
            setMessage(t('google.connected'));
            onChanged();
            break;
          }
        }
        // «Не подключён» уже написано в карточке — не дублируем.
      } else if (kind === 'import') {
        const result = await importFromGoogle();
        if (result.status === 'error' || result.errors.length > 0) {
          setError(
            t('google.importFailed', {
              error: result.errors.join('; ') || result.message,
            })
          );
        } else {
          setMessage(t('google.imported', { count: result.synced_items }));
        }
        onChanged();
      } else if (kind === 'clear') {
        const result = await clearGoogleCalendar();
        setMessage(t('google.cleared', { count: result.deleted }));
        onChanged();
      } else if (kind === 'disconnect') {
        const current = await disconnectGoogle();
        setStatus(current);
        setAuthUrl(null);
        setPopupBlocked(false);
        setMessage(t('google.disconnected'));
        onChanged();
      } else {
        const result = await exportPlanToGoogle();
        setMessage(
          result.failed > 0
            ? t('google.exportPartial', { count: result.exported, failed: result.failed })
            : t('google.exported', { count: result.exported })
        );
        onChanged();
      }
      void loadStatus();
    } catch (runError) {
      setError(t('google.failed', { error: getErrorMessage(runError) }));
    } finally {
      setBusy(null);
    }
  }

  const lastSync = status?.last_sync_at
    ? new Date(status.last_sync_at).toLocaleString(locale)
    : null;

  return (
    <div className="card google-panel">
      <div className="card-head">
        <div>
          <h2 className="card-title">{t('google.title')}</h2>
          <p className="card-note">
            {!status
              ? t('google.loading')
              : !status.configured
                ? t('google.notConfigured')
                : status.connected
                  ? lastSync
                    ? t('google.connectedSync', { time: lastSync })
                    : t('google.connected')
                  : t('google.notConnected')}
          </p>
        </div>
        <div className="google-panel-actions">
          {status?.configured && !status.connected && (
            <button
              className="button primary small"
              disabled={busy !== null}
              onClick={() => void run('connect')}
            >
              {busy === 'connect' ? t('google.connecting') : t('google.connect')}
            </button>
          )}
          {status?.connected && (
            <>
              <button
                className="button small"
                disabled={busy !== null}
                onClick={() => void run('import')}
              >
                {busy === 'import' ? t('google.importing') : t('google.import')}
              </button>
              <button
                className="button primary small"
                disabled={busy !== null}
                onClick={() => void run('export')}
              >
                {busy === 'export' ? t('google.exporting') : t('google.export')}
              </button>
              <button
                className="button small"
                disabled={busy !== null}
                onClick={() => void run('clear')}
              >
                {busy === 'clear' ? t('google.clearing') : t('google.clear')}
              </button>
              <button
                className="button small"
                disabled={busy !== null}
                onClick={() => void run('disconnect')}
              >
                {busy === 'disconnect'
                  ? t('google.disconnecting')
                  : t('google.disconnect')}
              </button>
            </>
          )}
        </div>
      </div>
      {busy === 'connect' && authUrl && !status?.connected && (
        <p className="card-note">
          {popupBlocked && <span>{t('google.popupBlocked')} </span>}
          <a href={authUrl} target="_blank" rel="noopener noreferrer">
            {t('google.authLink')}
          </a>
        </p>
      )}
      {message && <p className="card-note">{message}</p>}
      {error && <p className="card-note google-panel-error">{error}</p>}
    </div>
  );
}
