import { useCallback, useEffect, useState } from 'react';

import {
  connectGoogle,
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

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return 'Unknown error';
}

export function GoogleCalendarPanel({ onChanged }: GoogleCalendarPanelProps) {
  const { t, locale } = useSettings();
  const [status, setStatus] = useState<GoogleCalendarStatus | null>(null);
  const [busy, setBusy] = useState<'connect' | 'import' | 'export' | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const loadStatus = useCallback(async () => {
    try {
      setStatus(await getGoogleStatus());
    } catch (loadError) {
      setError(getErrorMessage(loadError));
    }
  }, []);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  async function run(kind: 'connect' | 'import' | 'export') {
    setBusy(kind);
    setMessage('');
    setError('');
    try {
      if (kind === 'connect') {
        setStatus(await connectGoogle());
        setMessage(t('google.connected'));
      } else if (kind === 'import') {
        const result = await importFromGoogle();
        setMessage(t('google.imported', { count: result.synced_items }));
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
            </>
          )}
        </div>
      </div>
      {message && <p className="card-note">{message}</p>}
      {error && <p className="card-note google-panel-error">{error}</p>}
    </div>
  );
}
