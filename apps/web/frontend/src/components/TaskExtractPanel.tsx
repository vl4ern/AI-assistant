import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import { extractTaskDraft } from '../api/taskExtract';
import { useSettings } from '../settings';
import { draftToTaskPayload, splitDraftDeadline } from '../taskDraft';
import type { ApiTaskCreate, ApiTaskDraft } from '../types/api';

const MAX_FILE_MB = 10;
const FILE_ACCEPT =
  '.txt,.md,.markdown,.csv,.json,.log,.yaml,.yml,' +
  'image/jpeg,image/png,image/webp,image/gif,image/bmp';

type InputMode = 'text' | 'file';

type TaskExtractPanelProps = {
  onCreate: (payload: ApiTaskCreate) => Promise<void>;
  onUseDraft: (draft: ApiTaskDraft) => void;
};

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return 'Неизвестная ошибка';
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} КБ`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

function formatDraftDeadline(
  value: string | null,
  locale: string,
  noDeadline: string
): string {
  const { date, time } = splitDraftDeadline(value);
  if (!date) return noDeadline;

  const parsed = new Date(`${date}T${time || '23:59'}:00`);
  if (Number.isNaN(parsed.getTime())) {
    return `${date} ${time}`.trim();
  }
  return parsed.toLocaleString(locale, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function TaskExtractPanel({ onCreate, onUseDraft }: TaskExtractPanelProps) {
  const { t, locale } = useSettings();
  const [isOpen, setIsOpen] = useState(false);
  const [mode, setMode] = useState<InputMode>('text');
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState('');
  const [draft, setDraft] = useState<ApiTaskDraft | null>(null);
  const [error, setError] = useState('');
  const [isExtracting, setIsExtracting] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const textAreaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (!file || !file.type.startsWith('image/')) {
      setPreviewUrl('');
      return undefined;
    }

    const objectUrl = URL.createObjectURL(file);
    setPreviewUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);

  useEffect(() => {
    if (!isOpen) return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [isOpen]);

  useEffect(() => {
    if (isOpen && !draft && mode === 'text') {
      textAreaRef.current?.focus();
    }
  }, [isOpen, draft, mode]);

  function resetInputs() {
    setMode('text');
    setText('');
    setFile(null);
    setDraft(null);
    setError('');
    setIsExtracting(false);
    setIsCreating(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }

  function openModal() {
    resetInputs();
    setIsOpen(true);
  }

  function closeModal() {
    setIsOpen(false);
    resetInputs();
  }

  function selectFile(nextFile: File | null) {
    if (!nextFile) return;
    if (nextFile.size > MAX_FILE_MB * 1024 * 1024) {
      setError(t('tasks.extract.fileTooLarge', { mb: MAX_FILE_MB }));
      setFile(null);
      return;
    }
    setError('');
    setFile(nextFile);
  }

  async function handleRecognize() {
    if (mode === 'text' && !text.trim()) {
      setError(t('tasks.extract.emptyInput'));
      return;
    }
    if (mode === 'file' && !file) {
      setError(t('tasks.extract.emptyInput'));
      return;
    }

    setIsExtracting(true);
    setError('');
    try {
      const result = await extractTaskDraft(
        mode === 'text' ? text : '',
        mode === 'file' ? file : null
      );
      setDraft(result);
    } catch (extractError) {
      setError(
        t('tasks.extract.error', { error: getErrorMessage(extractError) })
      );
    } finally {
      setIsExtracting(false);
    }
  }

  async function handleCreateNow() {
    if (!draft) return;

    setIsCreating(true);
    setError('');
    try {
      await onCreate(draftToTaskPayload(draft));
      closeModal();
    } catch (createError) {
      setError(
        t('tasks.extract.createError', { error: getErrorMessage(createError) })
      );
    } finally {
      setIsCreating(false);
    }
  }

  function handleUseDraft() {
    if (!draft) return;
    onUseDraft(draft);
    closeModal();
  }

  const canRecognize =
    !isExtracting && (mode === 'text' ? text.trim().length > 0 : file !== null);

  return (
    <>
      <button type="button" className="button ai-button" onClick={openModal}>
        <span className="ai-spark" aria-hidden="true">
          ✦
        </span>
        {t('tasks.extract.open')}
      </button>

      {isOpen &&
        createPortal(
          <div
            className="modal-backdrop"
            role="presentation"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) {
                closeModal();
              }
            }}
          >
            <div
              className="modal-card"
              role="dialog"
              aria-modal="true"
              aria-labelledby="task-extract-title"
            >
              <div className="modal-head">
                <div>
                  <h2 id="task-extract-title" className="modal-title">
                    {t('tasks.extract.title')}
                  </h2>
                  <p className="modal-subtitle">{t('tasks.extract.subtitle')}</p>
                </div>
                <button
                  type="button"
                  className="modal-close"
                  aria-label={t('tasks.extract.close')}
                  onClick={closeModal}
                >
                  ×
                </button>
              </div>

              {!draft ? (
                <>
                  <div className="extract-tabs" role="tablist">
                    <button
                      type="button"
                      role="tab"
                      aria-selected={mode === 'text'}
                      className={`extract-tab ${mode === 'text' ? 'active' : ''}`}
                      onClick={() => {
                        setMode('text');
                        setError('');
                      }}
                    >
                      {t('tasks.extract.tab.text')}
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={mode === 'file'}
                      className={`extract-tab ${mode === 'file' ? 'active' : ''}`}
                      onClick={() => {
                        setMode('file');
                        setError('');
                      }}
                    >
                      {t('tasks.extract.tab.file')}
                    </button>
                  </div>

                  {mode === 'text' ? (
                    <label className="field">
                      <span>{t('tasks.extract.textLabel')}</span>
                      <textarea
                        ref={textAreaRef}
                        className="input extract-textarea"
                        rows={6}
                        value={text}
                        onChange={(event) => setText(event.target.value)}
                        placeholder={t('tasks.extract.placeholder')}
                      />
                    </label>
                  ) : (
                    <>
                      <label
                        className="extract-dropzone"
                        onDragOver={(event) => event.preventDefault()}
                        onDrop={(event) => {
                          event.preventDefault();
                          selectFile(event.dataTransfer.files?.[0] ?? null);
                        }}
                      >
                        <input
                          ref={fileInputRef}
                          type="file"
                          accept={FILE_ACCEPT}
                          onChange={(event) =>
                            selectFile(event.target.files?.[0] ?? null)
                          }
                        />
                        <span className="extract-dropzone-title">
                          {file
                            ? file.name
                            : t('tasks.extract.chooseFile')}
                        </span>
                        <span className="extract-dropzone-hint">
                          {file
                            ? formatFileSize(file.size)
                            : t('tasks.extract.fileHint', { mb: MAX_FILE_MB })}
                        </span>
                      </label>
                      {previewUrl && (
                        <img
                          className="extract-preview-image"
                          src={previewUrl}
                          alt={t('tasks.extract.previewAlt')}
                        />
                      )}
                    </>
                  )}

                  {error && <div className="notice error">{error}</div>}

                  <div className="extract-note">
                    {t('tasks.extract.modelHint')}
                  </div>

                  <div className="modal-actions">
                    <button type="button" className="button" onClick={closeModal}>
                      {t('tasks.extract.cancel')}
                    </button>
                    <button
                      type="button"
                      className="button primary"
                      disabled={!canRecognize}
                      onClick={() => void handleRecognize()}
                    >
                      {isExtracting
                        ? t('tasks.extract.recognizing')
                        : t('tasks.extract.recognize')}
                    </button>
                  </div>
                </>
              ) : (
                <div className="extract-draft">
                  <div className="extract-draft-status">
                    <span className="extract-badge">
                      {t('tasks.extract.previewTitle')}
                    </span>
                    <span className="extract-source">
                      {draft.input_kind === 'image'
                        ? t('tasks.extract.sourceImage')
                        : t('tasks.extract.sourceText')}
                    </span>
                  </div>

                  <h3 className="extract-draft-title">{draft.title}</h3>
                  {draft.description && (
                    <p className="extract-draft-description">
                      {draft.description}
                    </p>
                  )}

                  <div className="extract-facts">
                    <div>
                      <span>{t('tasks.priority')}</span>
                      <strong>{t(`tasks.priority.${draft.priority}`)}</strong>
                    </div>
                    <div>
                      <span>{t('tasks.estimate')}</span>
                      <strong>
                        {draft.estimated_minutes} {t('task.minutes')}
                      </strong>
                    </div>
                    <div>
                      <span>{t('tasks.deadlineDate')}</span>
                      <strong>
                        {formatDraftDeadline(
                          draft.deadline,
                          locale,
                          t('task.noDeadline')
                        )}
                      </strong>
                    </div>
                  </div>

                  {draft.warnings.length > 0 && (
                    <ul className="extract-warnings">
                      {draft.warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  )}

                  {error && <div className="notice error">{error}</div>}

                  <div className="modal-actions">
                    <button
                      type="button"
                      className="button"
                      onClick={() => {
                        setDraft(null);
                        setError('');
                      }}
                    >
                      {t('tasks.extract.again')}
                    </button>
                    <button
                      type="button"
                      className="button"
                      onClick={handleUseDraft}
                    >
                      {t('tasks.extract.edit')}
                    </button>
                    <button
                      type="button"
                      className="button primary"
                      disabled={isCreating}
                      onClick={() => void handleCreateNow()}
                    >
                      {isCreating
                        ? t('tasks.extract.creating')
                        : t('tasks.extract.createNow')}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>,
          document.body
        )}
    </>
  );
}
