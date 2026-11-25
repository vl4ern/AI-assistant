import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import { extractTaskDraft } from '../api/taskExtract';
import { useSettings } from '../settings';
import { draftToTaskPayload, splitDraftDeadline } from '../taskDraft';
import type { ApiTaskCreate, ApiTaskDraft, ApiTaskDrafts } from '../types/api';

const MAX_FILE_MB = 10;
const MAX_FILES = 3;
const FILE_ACCEPT =
  '.txt,.md,.markdown,.csv,.json,.log,.yaml,.yml,.pdf,' +
  'image/jpeg,image/png,image/webp,image/gif,image/bmp';

type InputMode = 'text' | 'file';
type ViewMode = 'preview' | 'edit';

type TaskExtractPanelProps = {
  onCreate: (payload: ApiTaskCreate) => Promise<void>;
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

export function TaskExtractPanel({ onCreate }: TaskExtractPanelProps) {
  const { t, locale } = useSettings();
  const [isOpen, setIsOpen] = useState(false);
  const [mode, setMode] = useState<InputMode>('text');
  const [text, setText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [previewUrl, setPreviewUrl] = useState('');
  const [drafts, setDrafts] = useState<ApiTaskDraft[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [error, setError] = useState('');
  const [isExtracting, setIsExtracting] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('preview');

  // Редактируемая копия текущего черновика (режим «исправить в форме»).
  const [editTitle, setEditTitle] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editPriority, setEditPriority] = useState('3');
  const [editEstimate, setEditEstimate] = useState('60');
  const [editDeadlineDate, setEditDeadlineDate] = useState('');
  const [editDeadlineTime, setEditDeadlineTime] = useState('');

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const textAreaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const currentFile = files[0];
    if (!currentFile || !currentFile.type.startsWith('image/')) {
      setPreviewUrl('');
      return undefined;
    }

    const objectUrl = URL.createObjectURL(currentFile);
    setPreviewUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [files]);

  useEffect(() => {
    if (isOpen && !drafts.length && mode === 'text') {
      textAreaRef.current?.focus();
    }
  }, [isOpen, drafts, mode]);

  function resetInputs() {
    setMode('text');
    setText('');
    setFiles([]);
    setDrafts([]);
    setCurrentIndex(0);
    setError('');
    setIsExtracting(false);
    setIsCreating(false);
    setViewMode('preview');
    resetEditState();
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }

  function resetEditState() {
    setEditTitle('');
    setEditDescription('');
    setEditPriority('3');
    setEditEstimate('60');
    setEditDeadlineDate('');
    setEditDeadlineTime('');
  }

  function openModal() {
    resetInputs();
    setIsOpen(true);
  }

  function closeModal() {
    setIsOpen(false);
    resetInputs();
  }

  function selectFiles(next: FileList | null) {
    if (!next) return;

    const accepted: File[] = [];
    for (const candidate of Array.from(next)) {
      if (candidate.size > MAX_FILE_MB * 1024 * 1024) {
        setError(t('tasks.extract.fileTooLarge', { mb: MAX_FILE_MB }));
        return;
      }
      if (accepted.length >= MAX_FILES) {
        setError(t('tasks.extract.tooManyFiles', { count: MAX_FILES }));
        return;
      }
      accepted.push(candidate);
    }

    setFiles(accepted);
    setError('');
  }

  async function handleRecognize() {
    if (mode === 'text' && !text.trim()) {
      setError(t('tasks.extract.emptyInput'));
      return;
    }
    if (mode === 'file' && files.length === 0) {
      setError(t('tasks.extract.emptyInput'));
      return;
    }

    setIsExtracting(true);
    setError('');
    setViewMode('preview');
    try {
      const result: ApiTaskDrafts = await extractTaskDraft(
        mode === 'text' ? text : '',
        mode === 'file' ? files : []
      );
      const tasks = result.tasks ?? [];
      if (tasks.length === 0) {
        setError(t('tasks.extract.noTasks'));
        return;
      }
      setDrafts(tasks);
      setCurrentIndex(0);
    } catch (extractError) {
      setError(
        t('tasks.extract.error', { error: getErrorMessage(extractError) })
      );
    } finally {
      setIsExtracting(false);
    }
  }

  function getCurrentDraft(): ApiTaskDraft | undefined {
    return drafts[currentIndex];
  }

  function goPrev() {
    if (currentIndex > 0) {
      setCurrentIndex(currentIndex - 1);
      setViewMode('preview');
      setError('');
      resetEditState();
    }
  }

  function goNext() {
    if (currentIndex < drafts.length - 1) {
      setCurrentIndex(currentIndex + 1);
      setViewMode('preview');
      setError('');
      resetEditState();
    }
  }

  // Удаляет текущую задачу из предпросмотра (пропуск или после добавления).
  // Если задач больше не осталось — закрывает модал.
  function removeCurrentDraft() {
    const nextDrafts = drafts.filter((_, i) => i !== currentIndex);
    setDrafts(nextDrafts);
    if (nextDrafts.length === 0) {
      closeModal();
    } else {
      setCurrentIndex(Math.min(currentIndex, nextDrafts.length - 1));
      setViewMode('preview');
      setError('');
      resetEditState();
    }
  }

  async function handleCreateEdited() {
    const draft = getCurrentDraft();
    if (!draft) return;

    let deadline: string | null = null;
    if (editDeadlineDate) {
      const parsed = new Date(`${editDeadlineDate}T${editDeadlineTime || '23:59'}`);
      if (!Number.isNaN(parsed.getTime())) {
        deadline = parsed.toISOString();
      }
    }

    const payload: ApiTaskCreate = {
      title: editTitle.trim(),
      description: editDescription.trim() || null,
      estimated_minutes: Number(editEstimate) || 60,
      priority: Number(editPriority),
      deadline,
      workspace_id: draft.workspace_id,
      project_id: draft.project_id,
    };

    setIsCreating(true);
    setError('');
    try {
      await onCreate(payload);
      removeCurrentDraft();
    } catch (createError) {
      setError(
        t('tasks.extract.createError', { error: getErrorMessage(createError) })
      );
    } finally {
      setIsCreating(false);
    }
  }

  // Добавляет все оставшиеся черновики и закрывает модал.
  async function handleAddAll() {
    setIsCreating(true);
    setError('');
    try {
      const tasksToAdd = [...drafts];
      for (const draft of tasksToAdd) {
        await onCreate(draftToTaskPayload(draft));
      }
      closeModal();
    } catch (createError) {
      setError(
        t('tasks.extract.createError', { error: getErrorMessage(createError) })
      );
    } finally {
      setIsCreating(false);
    }
  }

  function startEdit() {
    const draft = getCurrentDraft();
    if (!draft) return;

    const { date, time } = splitDraftDeadline(draft.deadline);
    setEditTitle(draft.title);
    setEditDescription(draft.description ?? '');
    setEditPriority(String(draft.priority));
    setEditEstimate(String(draft.estimated_minutes));
    setEditDeadlineDate(date);
    setEditDeadlineTime(time);
    setViewMode('edit');
    setError('');
  }

  function cancelEdit() {
    setViewMode('preview');
    resetEditState();
    setError('');
  }

  const currentDraft = getCurrentDraft();
  const isLastTask = currentIndex >= drafts.length - 1;
  const isFirstTask = currentIndex <= 0;

  const canRecognize =
    !isExtracting && (mode === 'text' ? text.trim().length > 0 : files.length > 0);

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

              {currentDraft ? (
                <div className="extract-draft">
                  <div className="extract-draft-status">
                    <span className="extract-badge">
                      {t('tasks.extract.previewTitle')}
                    </span>
                    <span className="extract-source">
                      {currentDraft.input_kind === 'image'
                        ? t('tasks.extract.sourceImage')
                        : t('tasks.extract.sourceText')}
                    </span>
                  </div>

                  {drafts.length > 1 && (
                    <div className="extract-navigation">
                      <span className="extract-navigation-counter">
                        {t('tasks.extract.taskNumber', {
                          current: currentIndex + 1,
                          total: drafts.length,
                        })}
                      </span>
                      <button
                        type="button"
                        className={`button small ${isFirstTask ? 'disabled' : ''}`}
                        disabled={isFirstTask || isCreating}
                        aria-label={t('tasks.extract.prevTask')}
                        onClick={goPrev}
                      >
                        ←
                      </button>
                      <button
                        type="button"
                        className={`button small ${isLastTask ? 'disabled' : ''}`}
                        disabled={isLastTask || isCreating}
                        aria-label={t('tasks.extract.nextTask')}
                        onClick={goNext}
                      >
                        →
                      </button>
                    </div>
                  )}

                  {viewMode === 'edit' ? (
                    <div className="extract-edit-form">
                      <label className="field span-2">
                        <span>{t('tasks.what')}</span>
                        <input
                          className="input"
                          value={editTitle}
                          onChange={(event) => setEditTitle(event.target.value)}
                        />
                      </label>
                      <label className="field span-2">
                        <span>{t('tasks.note')}</span>
                        <textarea
                          className="input"
                          rows={3}
                          value={editDescription}
                          onChange={(event) => setEditDescription(event.target.value)}
                        />
                      </label>
                      <div className="form-grid">
                        <label className="field">
                          <span>{t('tasks.priority')}</span>
                          <select
                            className="input"
                            value={editPriority}
                            onChange={(event) => setEditPriority(event.target.value)}
                          >
                            <option value="1">{t('tasks.priority.1')}</option>
                            <option value="2">{t('tasks.priority.2')}</option>
                            <option value="3">{t('tasks.priority.3')}</option>
                            <option value="4">{t('tasks.priority.4')}</option>
                          </select>
                        </label>
                        <label className="field">
                          <span>{t('tasks.estimate')}</span>
                          <input
                            className="input"
                            type="number"
                            min={15}
                            step={15}
                            value={editEstimate}
                            onChange={(event) => setEditEstimate(event.target.value)}
                          />
                        </label>
                      </div>
                      <div className="form-grid">
                        <label className="field">
                          <span>{t('tasks.deadlineDate')}</span>
                          <input
                            className="input"
                            type="date"
                            value={editDeadlineDate}
                            onChange={(event) =>
                              setEditDeadlineDate(event.target.value)
                            }
                          />
                        </label>
                        <label className="field">
                          <span>{t('tasks.time')}</span>
                          <input
                            className="input"
                            type="time"
                            value={editDeadlineTime}
                            onChange={(event) =>
                              setEditDeadlineTime(event.target.value)
                            }
                          />
                        </label>
                      </div>
                      {currentDraft.warnings.length > 0 && (
                        <ul className="extract-warnings">
                          {currentDraft.warnings.map((warning) => (
                            <li key={warning}>{warning}</li>
                          ))}
                        </ul>
                      )}
                      {error && <div className="notice error">{error}</div>}
                      <div className="modal-actions" style={{ marginTop: '20px' }}>
                        <button
                          type="button"
                          className="button"
                          onClick={cancelEdit}
                          disabled={isCreating}
                        >
                          {t('tasks.extract.cancel')}
                        </button>
                        <button
                          type="button"
                          className="button primary"
                          disabled={isCreating || editTitle.trim().length === 0}
                          onClick={handleCreateEdited}
                        >
                          {isCreating
                            ? t('tasks.extract.creating')
                            : t('tasks.create')}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <h3 className="extract-draft-title">{currentDraft.title}</h3>
                      {currentDraft.description && (
                        <p className="extract-draft-description">
                          {currentDraft.description}
                        </p>
                      )}

                      <div className="extract-facts">
                        <div>
                          <span>{t('tasks.priority')}</span>
                          <strong>{t(`tasks.priority.${currentDraft.priority}`)}</strong>
                        </div>
                        <div>
                          <span>{t('tasks.estimate')}</span>
                          <strong>
                            {currentDraft.estimated_minutes} {t('task.minutes')}
                          </strong>
                        </div>
                        <div>
                          <span>{t('tasks.deadlineDate')}</span>
                          <strong>
                            {formatDraftDeadline(
                              currentDraft.deadline,
                              locale,
                              t('task.noDeadline')
                            )}
                          </strong>
                        </div>
                      </div>

                      {currentDraft.warnings.length > 0 && (
                        <ul className="extract-warnings">
                          {currentDraft.warnings.map((warning) => (
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
                            setDrafts([]);
                            setCurrentIndex(0);
                            setError('');
                            setViewMode('preview');
                          }}
                        >
                          {t('tasks.extract.again')}
                        </button>
                        <button
                          type="button"
                          className="button"
                          onClick={startEdit}
                          disabled={isCreating}
                        >
                          {t('tasks.extract.edit')}
                        </button>
                        <button
                          type="button"
                          className="button"
                          onClick={removeCurrentDraft}
                          disabled={isCreating}
                        >
                          {t('tasks.extract.skip')}
                        </button>
                        <button
                          type="button"
                          className="button primary"
                          disabled={isCreating}
                          onClick={handleAddAll}
                        >
                          {isCreating
                            ? t('tasks.extract.creating')
                            : t('tasks.extract.createNow')}
                        </button>
                      </div>
                    </>
                  )}
                </div>
              ) : (
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
                          selectFiles(event.dataTransfer.files);
                        }}
                      >
                        <input
                          ref={fileInputRef}
                          type="file"
                          accept={FILE_ACCEPT}
                          multiple
                          onChange={(event) =>
                            selectFiles(event.target.files)
                          }
                        />
                        <span className="extract-dropzone-title">
                          {files.length > 0
                            ? files.map((file) => file.name).join(', ')
                            : t('tasks.extract.chooseFile')}
                        </span>
                        <span className="extract-dropzone-hint">
                          {files.length > 0
                            ? files.map((file) => formatFileSize(file.size)).join(' · ')
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
              )}
            </div>
          </div>,
          document.body
        )}
    </>
  );
}
