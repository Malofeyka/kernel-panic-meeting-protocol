import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeftIcon, CheckIcon } from '@phosphor-icons/react'
import {
  api,
  ApiError,
  type ProcessingStep,
  type ProtocolDraft,
  type SessionDetails,
  type SessionStatusResponse,
} from '@/api'
import { ReviewScreen, type Outcome } from '@/features/review/ReviewScreen'
import { cx } from '@/lib/cx'
import { ruLongDate } from '@/lib/dates'
import { errorText } from '@/lib/errorText'
import { usePolling } from '@/lib/usePolling'
import { Button } from '@/ui/Button'
import { Notice } from '@/ui/Notice'
import { ProgressBar } from '@/ui/ProgressBar'
import { Spinner } from '@/ui/Spinner'
import { BUSY, stepIndex, stepsFor } from './steps'

interface Props {
  sessionId: string
  onNew: () => void
}

/**
 * Рабочая сессия: обработка → проверка и правка проекта → скачивание.
 * Состояние берётся с сервера (GET /sessions/{id}), поэтому переживает перезагрузку страницы.
 */
export function SessionView({ sessionId, onNew }: Props) {
  const [info, setInfo] = useState<SessionDetails | null>(null)
  const [status, setStatus] = useState<SessionStatusResponse | null>(null)
  const [draft, setDraft] = useState<ProtocolDraft | null>(null)
  const [fatal, setFatal] = useState<unknown>(null)
  const [offline, setOffline] = useState(false)
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const [retrying, setRetrying] = useState(false)
  const last = useRef<ProcessingStep | null>(null)
  const dirty = useRef(false)

  const loadDraft = useCallback(
    () =>
      api
        .getDraft(sessionId)
        .then(setDraft)
        .catch((e: unknown) => setFatal(e)),
    [sessionId],
  )

  useEffect(() => {
    let alive = true
    api
      .getSession(sessionId)
      .then((d) => {
        if (!alive) return
        setInfo(d)
        setStatus(d)
        last.current = d.status
        if (d.has_draft) void loadDraft()
      })
      .catch((e: unknown) => alive && setFatal(e))
    return () => {
      alive = false
    }
  }, [sessionId, loadDraft])

  // Несохранённые правки: предупреждаем при закрытии вкладки
  useEffect(() => {
    const guard = (e: BeforeUnloadEvent) => {
      if (dirty.current) e.preventDefault()
    }
    window.addEventListener('beforeunload', guard)
    return () => window.removeEventListener('beforeunload', guard)
  }, [])

  const busy = status !== null && BUSY.has(status.status)

  usePolling(
    async () => {
      try {
        const next = await api.getStatus(sessionId)
        setOffline(false)
        const prev = last.current
        last.current = next.status
        setStatus(next)
        if (next.status === 'ready' && prev !== 'ready') {
          await loadDraft()
          if (prev === 'refining') {
            // Итог правки — в описании шага; ошибка правки не меняет проект
            setOutcome(
              next.error_message
                ? { tone: 'warning', text: next.error_message }
                : { tone: 'success', text: next.current_step_description },
            )
          }
        }
        return BUSY.has(next.status)
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) {
          setFatal(e)
          return false
        }
        setOffline(true)
        return true
      }
    },
    { enabled: busy && !fatal },
  )

  const leave = () => {
    if (dirty.current && !window.confirm('Есть несохранённые изменения. Уйти без сохранения?'))
      return
    onNew()
  }

  const retry = async () => {
    setRetrying(true)
    try {
      const next = await api.restartProcessing(sessionId)
      last.current = next.status
      setStatus(next)
    } catch (e) {
      setFatal(e)
    } finally {
      setRetrying(false)
    }
  }

  const onDirtyChange = useCallback((d: boolean) => {
    dirty.current = d
  }, [])

  const back = (
    <Button variant="link" onClick={leave} icon={<ArrowLeftIcon size={16} />}>
      Новый протокол
    </Button>
  )
  const again = <Button onClick={onNew}>Загрузить заново</Button>

  const reviewing =
    draft !== null && info !== null && (status?.status === 'ready' || status?.status === 'refining')
  if (reviewing && !fatal) {
    return (
      <>
        {back}
        <div className="mt-4">
          <ReviewScreen
            sessionId={sessionId}
            draft={draft}
            refining={status?.status === 'refining'}
            outcome={outcome}
            onDismissOutcome={() => setOutcome(null)}
            onDraft={setDraft}
            onRefineStarted={(s) => {
              last.current = s.status
              setStatus(s)
            }}
            onDirtyChange={onDirtyChange}
          />
        </div>
      </>
    )
  }

  let body
  if (fatal) {
    const t = errorText(fatal)
    body = (
      <Notice title={t.title} action={again}>
        {t.hint}
      </Notice>
    )
  } else if (!status || !info || status.status === 'ready' || status.status === 'refining') {
    body = (
      <p className="flex items-center gap-2 text-ink-3">
        <Spinner /> Загрузка…
      </p>
    )
  } else if (status.status === 'idle') {
    body = (
      <Notice tone="warning" title="Файлы не были загружены" action={again}>
        Загрузка прервалась до отправки записи.
      </Notice>
    )
  } else if (status.status === 'failed') {
    body = (
      <Notice
        title="Не удалось подготовить протокол"
        action={
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" loading={retrying} onClick={() => void retry()}>
              Повторить обработку
            </Button>
            {again}
          </div>
        }
      >
        {status.error_message ?? 'Сервер не сообщил причину. Попробуйте ещё раз.'}
      </Notice>
    )
  } else {
    body = <Progress status={status} offline={offline} fromTranscript={!!info.files.transcript} />
  }

  return (
    <div className="max-w-[880px]">
      {back}
      <h1 className="mt-4 text-[32px] leading-10 font-semibold tracking-[-0.01em]">
        {info?.meeting_title ?? 'Совещание'}
      </h1>
      {info && <p className="mt-1 text-[17px] text-ink-2">{ruLongDate(info.meeting_date)}</p>}
      <div className="mt-8">{body}</div>
    </div>
  )
}

function Progress({
  status,
  offline,
  fromTranscript,
}: {
  status: SessionStatusResponse
  offline: boolean
  fromTranscript: boolean
}) {
  const current = stepIndex(status.status)
  return (
    <div className="rounded-[var(--radius-card)] border border-line bg-surface px-8 py-7">
      <p className="flex items-center gap-3 text-[19px] leading-7 font-semibold">
        <Spinner className="size-5 text-primary" />
        {fromTranscript ? 'Идёт обработка стенограммы' : 'Идёт обработка записи'}
      </p>
      <div className="mt-5">
        <ProgressBar label="Ход обработки" value={status.progress_percent} />
      </div>
      <p className="mt-4 text-ink-3" aria-live="polite">
        {offline
          ? 'Нет связи с сервером. Обработка продолжается, статус обновится автоматически.'
          : fromTranscript
            ? 'Обычно это занимает несколько минут. Страницу можно закрыть — проект откроется из списка на стартовой странице.'
            : 'Обработка записи длительностью 1–1,5 часа занимает до 45 минут. Страницу можно закрыть — проект откроется из списка на стартовой странице.'}
      </p>
      <ol className="mt-6 flex flex-col gap-3 border-t border-line pt-6">
        {stepsFor(fromTranscript).map((label, i) => {
          const state = i < current ? 'done' : i === current ? 'active' : 'todo'
          return (
            <li key={label} className="flex items-center gap-3">
              <span
                className={cx(
                  'flex size-6 shrink-0 items-center justify-center rounded-full',
                  state === 'done' && 'bg-success text-white',
                  state === 'active' && 'border-2 border-primary',
                  state === 'todo' && 'border-2 border-line-strong',
                )}
              >
                {state === 'done' && <CheckIcon size={14} weight="bold" />}
                {state === 'active' && <span className="size-2 rounded-full bg-primary" />}
              </span>
              <span className={state === 'todo' ? 'text-ink-3' : 'text-ink'}>{label}</span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
