import { useEffect, useReducer, useState } from 'react'
import { DownloadSimpleIcon, XIcon } from '@phosphor-icons/react'
import { api, ApiError, type ProtocolDraft, type SessionStatusResponse } from '@/api'
import { cx } from '@/lib/cx'
import { ruLongDate } from '@/lib/dates'
import { errorText } from '@/lib/errorText'
import { locateAction } from '@/lib/protocol'
import { Button, IconButton } from '@/ui/Button'
import { Notice } from '@/ui/Notice'
import { editorReducer, prepareForSave } from './draftReducer'
import { IssuesPanel, type IssueTarget } from './IssuesPanel'
import { ProtocolEditor } from './ProtocolEditor'
import { RefinePanel } from './RefinePanel'
import { TranscriptPanel, type TranscriptFocus } from './TranscriptPanel'

export interface Outcome {
  tone: 'success' | 'warning'
  text: string
}

interface Props {
  sessionId: string
  /** Последняя версия проекта с сервера */
  draft: ProtocolDraft
  refining: boolean
  outcome: Outcome | null
  onDismissOutcome: () => void
  /** Сервер вернул новую версию проекта */
  onDraft: (draft: ProtocolDraft) => void
  /** ИИ-правка запущена — родитель начинает опрос статуса */
  onRefineStarted: (status: SessionStatusResponse) => void
  /** Есть несохранённые правки — нужно предупредить перед уходом */
  onDirtyChange: (dirty: boolean) => void
}

type Tab = 'issues' | 'transcript'

/** Подсветка строки документа, на которую указывает замечание */
function flash(id: string) {
  const el = document.getElementById(id)
  if (!el) return
  el.scrollIntoView({ block: 'center', behavior: 'smooth' })
  el.classList.add('bg-primary-soft', 'ring-2', 'ring-primary/40')
  setTimeout(() => el.classList.remove('bg-primary-soft', 'ring-2', 'ring-primary/40'), 1800)
  el.querySelector<HTMLElement>('textarea, input')?.focus({ preventScroll: true })
}

/** Скачивание: download_url — ссылка бэкенда (имя файла в Content-Disposition) */
function download(url: string, fileName: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  document.body.append(a)
  a.click()
  a.remove()
}

export function ReviewScreen({
  sessionId,
  draft,
  refining,
  outcome,
  onDismissOutcome,
  onDraft,
  onRefineStarted,
  onDirtyChange,
}: Props) {
  const [state, dispatch] = useReducer(editorReducer, { draft, dirty: false })
  const [tab, setTab] = useState<Tab>('issues')
  const [focus, setFocus] = useState<TranscriptFocus | null>(null)
  const [busy, setBusy] = useState<'save' | 'export' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refineError, setRefineError] = useState<string | null>(null)
  const [exportWarnings, setExportWarnings] = useState<string[]>([])
  const [saved, setSaved] = useState(false)

  // Новая версия с сервера (сохранение, итог ИИ-правки) заменяет локальную копию
  useEffect(() => dispatch({ type: 'reset', draft }), [draft])
  useEffect(() => onDirtyChange(state.dirty), [state.dirty, onDirtyChange])
  useEffect(() => {
    if (!saved) return
    const t = setTimeout(() => setSaved(false), 2500)
    return () => clearTimeout(t)
  }, [saved])

  const edited = state.draft
  const locked = refining || busy !== null

  const prepared = () => {
    const p = prepareForSave(edited)
    if (!p.ok) {
      setError(p.message)
      flash(p.target)
      return null
    }
    setError(null)
    return p.draft
  }

  const save = async (): Promise<boolean> => {
    const d = prepared()
    if (!d) return false
    setBusy('save')
    try {
      const r = await api.refine(sessionId, {
        action: 'manual_save',
        updated_agenda_items: d.agenda_items,
        updated_metadata: d.metadata,
      })
      onDraft(r.updated_draft)
      setSaved(true)
      return true
    } catch (e) {
      const t = errorText(e)
      setError(`${t.title}. ${t.hint}`)
      return false
    } finally {
      setBusy(null)
    }
  }

  const exportDocx = async () => {
    if (state.dirty && !(await save())) return
    setBusy('export')
    setExportWarnings([])
    try {
      const e = await api.exportDocx(sessionId)
      setExportWarnings(e.warnings)
      download(e.download_url, e.file_name)
    } catch (e) {
      const t = errorText(e)
      setError(`${t.title}. ${t.hint}`)
    } finally {
      setBusy(null)
    }
  }

  const refine = async (feedback: string): Promise<boolean> => {
    const d = prepared()
    if (!d) return false
    setRefineError(null)
    onDismissOutcome()
    try {
      const r = await api.refine(sessionId, {
        action: 'ai_regenerate',
        user_feedback: feedback,
        updated_agenda_items: d.agenda_items,
        updated_metadata: d.metadata,
      })
      onDraft(r.updated_draft)
      if (r.status === 'refining') {
        onRefineStarted({
          session_id: sessionId,
          status: 'refining',
          progress_percent: 50,
          current_step_description: r.message,
          error_message: null,
          updated_at: new Date().toISOString(),
        })
      } else {
        setRefineError(r.message)
      }
      return true
    } catch (e) {
      // Лимит исчерпан: сервер сохранил правки и перевёл сессию в ручной режим
      if (e instanceof ApiError && e.status === 400) {
        const fresh = await api.getDraft(sessionId).catch(() => null)
        if (fresh) onDraft(fresh)
      }
      setRefineError(e instanceof Error ? e.message : String(e))
      return false
    }
  }

  const pick = (t: IssueTarget) => {
    const found = t.actionId ? locateAction(edited, t.actionId) : null
    if (found?.action.id) flash(`row-${found.action.id}`)
    else if (t.agendaItem) flash(`item-${t.agendaItem}`)
    else if (t.quote) showQuote(t.quote, t.start)
  }

  const showQuote = (quote: string, start: number | null) => {
    setTab('transcript')
    setFocus({ quote, start, nonce: Date.now() })
  }

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-[32px] leading-10 font-semibold tracking-[-0.01em]">
            {edited.metadata.meeting_title || 'Совещание'}
          </h1>
          <p className="mt-1 text-[17px] text-ink-2">{ruLongDate(edited.metadata.meeting_date)}</p>
        </div>
        <Button
          variant="primary"
          icon={<DownloadSimpleIcon size={18} />}
          loading={busy === 'export'}
          disabled={locked && busy !== 'export'}
          onClick={() => void exportDocx()}
        >
          Скачать протокол
        </Button>
      </div>

      {exportWarnings.length > 0 && (
        <Notice tone="warning" className="mt-6" title="Документ сформирован с замечаниями">
          <ul className="list-disc pl-5">
            {exportWarnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </Notice>
      )}

      <div className="mt-8 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <fieldset disabled={locked} className={cx('min-w-0', refining && 'opacity-60')}>
          <legend className="sr-only">Проект протокола</legend>
          <ProtocolEditor draft={edited} dispatch={dispatch} onQuote={showQuote} />
        </fieldset>

        <aside className="flex flex-col overflow-hidden rounded-[var(--radius-card)] border border-line bg-surface lg:sticky lg:top-6 lg:max-h-[calc(100dvh-48px)]">
          {outcome && (
            <div
              role="status"
              className={cx(
                'flex items-start gap-2 border-b border-line px-5 py-3',
                outcome.tone === 'success' ? 'bg-success-soft' : 'bg-warning-soft',
              )}
            >
              <p className="flex-1">{outcome.text}</p>
              <IconButton label="Скрыть" className="-mr-2 size-7" onClick={onDismissOutcome}>
                <XIcon size={14} />
              </IconButton>
            </div>
          )}
          <div role="tablist" className="flex border-b border-line px-3">
            {(
              [
                ['issues', 'Замечания'],
                ['transcript', 'Стенограмма'],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
                className={cx(
                  '-mb-px cursor-pointer border-b-2 px-2 py-3 font-medium transition-colors not-first:ml-4',
                  tab === id
                    ? 'border-primary text-ink'
                    : 'border-transparent text-ink-3 hover:text-ink',
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="min-h-40 flex-1 overflow-y-auto">
            {tab === 'issues' ? (
              <IssuesPanel analytics={draft.analytics} draft={edited} onPick={pick} />
            ) : (
              <TranscriptPanel sessionId={sessionId} focus={focus} />
            )}
          </div>
          <div className="border-t border-line bg-subtle">
            <RefinePanel
              cycle={edited.revision_cycle}
              refining={refining}
              error={refineError}
              onSubmit={refine}
            />
          </div>
        </aside>
      </div>

      {(state.dirty || saved || error) && (
        <div className="sticky bottom-0 z-30 mt-6 border-t border-line bg-surface/95 backdrop-blur-sm">
          <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-2 py-3">
            <p
              aria-live="polite"
              className={cx(
                'mr-auto',
                error ? 'text-danger' : saved ? 'text-success' : 'text-ink-2',
              )}
            >
              {error ?? (state.dirty ? 'Есть несохранённые изменения' : 'Изменения сохранены')}
            </p>
            {state.dirty && (
              <>
                <Button
                  variant="link"
                  disabled={locked}
                  onClick={() => {
                    setError(null)
                    dispatch({ type: 'reset', draft })
                  }}
                >
                  Отменить изменения
                </Button>
                <Button
                  variant="primary"
                  loading={busy === 'save'}
                  disabled={locked && busy !== 'save'}
                  onClick={() => void save()}
                >
                  Сохранить
                </Button>
              </>
            )}
          </div>
        </div>
      )}
    </>
  )
}
