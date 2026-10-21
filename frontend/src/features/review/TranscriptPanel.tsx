import { useEffect, useRef, useState } from 'react'
import { api, type MeetingTranscription, type TranscriptionSegment } from '@/api'
import { cx } from '@/lib/cx'
import { errorText } from '@/lib/errorText'
import { Spinner } from '@/ui/Spinner'

export interface TranscriptFocus {
  quote: string
  start: number | null
  /** Повторный клик по той же цитате тоже должен прокрутить */
  nonce: number
}

const norm = (s: string) =>
  s
    .toLowerCase()
    .replace(/[«»"„“.,!?;:—–-]/g, '')
    .replace(/\s+/g, ' ')
    .trim()

/** Сегмент, к которому относится цитата: по тексту, иначе по таймкоду */
export function findSegment(segments: TranscriptionSegment[], quote: string, start: number | null) {
  const q = norm(quote)
  const byText = segments.findIndex((s) => {
    const t = norm(s.text)
    return t.length > 0 && (t.includes(q) || q.includes(t))
  })
  if (byText >= 0) return byText
  if (start == null) return -1
  let found = -1
  segments.forEach((s, i) => {
    if (s.start <= start) found = i
  })
  return found
}

function timecode(sec: number) {
  const s = Math.floor(sec)
  const h = Math.floor(s / 3600)
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, '0')
  const ss = String(s % 60).padStart(2, '0')
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

export function TranscriptPanel({
  sessionId,
  focus,
}: {
  sessionId: string
  focus: TranscriptFocus | null
}) {
  const [data, setData] = useState<MeetingTranscription | null>(null)
  const [error, setError] = useState<unknown>(null)
  const list = useRef<HTMLOListElement>(null)

  useEffect(() => {
    let alive = true
    api
      .getTranscript(sessionId)
      .then((t) => alive && setData(t))
      .catch((e: unknown) => alive && setError(e))
    return () => {
      alive = false
    }
  }, [sessionId])

  const active = data && focus ? findSegment(data.segments, focus.quote, focus.start) : -1

  useEffect(() => {
    if (active < 0) return
    list.current?.children[active]?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [active, focus?.nonce])

  if (error) {
    const t = errorText(error)
    return <p className="px-5 py-4 text-ink-2">{t.title}</p>
  }
  if (!data) {
    return (
      <p className="flex items-center gap-2 px-5 py-4 text-ink-3">
        <Spinner /> Загрузка стенограммы…
      </p>
    )
  }
  // Стенограмма из текстового файла приходит без таймкодов
  const timed = data.segments.some((s) => s.start > 0)
  return (
    <ol ref={list} className="py-3">
      {data.segments.map((s, i) => (
        <li
          key={i}
          className={cx(
            'flex gap-3 px-5 py-1.5 transition-colors',
            i === active && 'bg-warning-soft',
          )}
        >
          {timed && (
            <span className="w-11 shrink-0 pt-px text-sm text-ink-3 tabular-nums">
              {timecode(s.start)}
            </span>
          )}
          <span>{s.text}</span>
        </li>
      ))}
    </ol>
  )
}
