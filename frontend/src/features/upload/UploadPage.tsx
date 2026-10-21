import { useRef, useState, type ReactNode, type SubmitEvent } from 'react'
import { api, isAbortError } from '@/api'
import { isoToRu } from '@/lib/dates'
import { errorText } from '@/lib/errorText'
import { DOC_SLOTS } from '@/lib/files'
import { useFileDrop } from '@/lib/useFileDrop'
import { useServerDown } from '@/lib/useServerDown'
import { Button } from '@/ui/Button'
import { Field } from '@/ui/Field'
import { Notice } from '@/ui/Notice'
import { ProgressBar } from '@/ui/ProgressBar'
import { AudioDrop } from './AudioDrop'
import { DocSlotRow } from './DocSlotRow'
import { RecentSessions } from './RecentSessions'
import { UnsortedFiles } from './UnsortedFiles'
import { pickedFor, useUploadForm } from './useUploadForm'

type Sending = { loaded: number; total: number } | 'create'

interface Props {
  onStarted: (sessionId: string) => void
  onOpen: (sessionId: string) => void
}

export function UploadPage({ onStarted, onOpen }: Props) {
  const { state, dispatch, summary, files } = useUploadForm()
  const [sending, setSending] = useState<Sending | null>(null)
  const [error, setError] = useState<unknown>(null)
  const abort = useRef<AbortController | null>(null)
  const serverDown = useServerDown()
  const busy = sending !== null

  // Файлы можно бросить на любую часть страницы — разложатся по назначению
  const page = useFileDrop((dropped) => dispatch({ type: 'batch', files: dropped }), busy)

  const submit = async (e: SubmitEvent<HTMLFormElement>) => {
    e.preventDefault()
    const payload = files()
    if (!payload || busy) return
    const ctrl = new AbortController()
    abort.current = ctrl
    setError(null)
    setSending('create')
    try {
      const { session_id } = await api.createSession({
        meeting_title: state.title.trim(),
        meeting_date: isoToRu(state.date),
      })
      if (ctrl.signal.aborted) throw new DOMException('Загрузка отменена', 'AbortError')
      await api.uploadFiles(session_id, payload, { signal: ctrl.signal, onProgress: setSending })
      onStarted(session_id)
    } catch (err) {
      if (!isAbortError(err)) setError(err)
      setSending(null)
    }
  }

  const err = error ? errorText(error) : null
  const percent =
    sending && sending !== 'create' && sending.total ? (sending.loaded / sending.total) * 100 : 0

  return (
    <div {...page.props}>
      <h1 className="text-[32px] leading-10 font-semibold tracking-[-0.01em]">Новый протокол</h1>
      <p className="mt-2 text-[17px] text-ink-2">
        Загрузите аудиозапись совещания — система подготовит проект протокола с решениями,
        поручениями, сроками и ответственными.
      </p>

      {serverDown && (
        <Notice className="mt-6" title="Сервер не отвечает">
          Обработка сейчас недоступна. Проверьте, что серверная часть запущена на этом компьютере.
        </Notice>
      )}

      <form
        onSubmit={submit}
        className="mt-8 overflow-hidden rounded-[var(--radius-card)] border border-line bg-surface"
      >
        <Section title="Сведения о совещании">
          <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_200px]">
            <Field
              label="Наименование"
              value={state.title}
              onChange={(e) => dispatch({ type: 'field', name: 'title', value: e.target.value })}
              disabled={busy}
              maxLength={200}
              required
            />
            <Field
              label="Дата проведения"
              type="date"
              value={state.date}
              onChange={(e) => dispatch({ type: 'field', name: 'date', value: e.target.value })}
              disabled={busy}
              required
            />
          </div>
        </Section>

        <Section title="Запись совещания">
          <AudioDrop
            audio={state.audio}
            transcript={state.transcript}
            duration={state.audioDuration}
            onAudio={(f) => dispatch({ type: 'put', slot: 'audio', files: f })}
            onTranscript={(f) => dispatch({ type: 'put', slot: 'transcript', files: f })}
            onRemove={() => dispatch({ type: 'remove', slot: 'audio' })}
            disabled={busy}
          />
        </Section>

        <Section
          title="Материалы к совещанию"
          hint="Необязательно. Помогают точнее разбить протокол по вопросам повестки и определить ответственных."
        >
          <ul className="-my-3.5 divide-y divide-line">
            {DOC_SLOTS.map((slot) => (
              <DocSlotRow
                key={slot}
                slot={slot}
                picked={pickedFor(state, slot)}
                onFiles={(f) => dispatch({ type: 'put', slot, files: f })}
                onRemove={(key) => dispatch({ type: 'remove', slot, key })}
                disabled={busy}
              />
            ))}
          </ul>
          <UnsortedFiles
            files={state.unsorted}
            onAssign={(key, slot) => dispatch({ type: 'assign', key, slot })}
            onDismiss={(key) => dispatch({ type: 'dismiss', key })}
            disabled={busy}
          />
        </Section>

        <div className="flex flex-wrap items-center justify-end gap-x-6 gap-y-3 bg-subtle px-8 py-5">
          {err && (
            <p role="alert" className="mr-auto text-danger">
              {err.title}. {err.hint}
            </p>
          )}
          {sending ? (
            <>
              <div className="mr-auto flex min-w-60 flex-1 flex-col gap-2" aria-live="polite">
                <span className="text-ink-2">
                  {sending === 'create' ? 'Подготовка…' : 'Загрузка файлов…'}
                </span>
                <ProgressBar label="Загрузка файлов" value={percent} />
              </div>
              <Button onClick={() => abort.current?.abort()}>Отменить</Button>
            </>
          ) : (
            <>
              {summary.blocker && !err && <p className="mr-auto text-ink-3">{summary.blocker}</p>}
              <Button type="submit" variant="primary" disabled={!!summary.blocker}>
                Сформировать проект протокола
              </Button>
            </>
          )}
        </div>
      </form>

      {!busy && <RecentSessions onOpen={onOpen} />}

      {page.over && (
        <div className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center bg-page/85 p-6">
          <div className="rounded-[var(--radius-card)] border-2 border-dashed border-primary bg-surface px-10 py-8 text-center text-[17px] font-medium">
            Отпустите, чтобы добавить файлы
          </div>
        </div>
      )}
    </div>
  )
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="border-b border-line px-8 py-7">
      <h2 className="text-[19px] leading-7 font-semibold">{title}</h2>
      {hint && <p className="mt-1 max-w-[620px] text-ink-3">{hint}</p>}
      <div className="mt-5">{children}</div>
    </section>
  )
}
