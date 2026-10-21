import { useEffect, useState } from 'react'
import { CaretRightIcon } from '@phosphor-icons/react'
import { api, type ProcessingStep, type SessionSummary } from '@/api'
import { cx } from '@/lib/cx'

const LIMIT = 5

const STATE: Partial<Record<ProcessingStep, { text: string; className: string }>> = {
  ready: { text: 'Проект готов', className: 'text-success' },
  refining: { text: 'Доработка', className: 'text-ink-3' },
  uploading: { text: 'Обработка', className: 'text-ink-3' },
  transcribing: { text: 'Обработка', className: 'text-ink-3' },
  extracting: { text: 'Обработка', className: 'text-ink-3' },
  cross_checking: { text: 'Обработка', className: 'text-ink-3' },
  failed: { text: 'Ошибка', className: 'text-danger' },
}

/** Ранее загруженные совещания — чтобы вернуться к проекту после перерыва */
export function RecentSessions({ onOpen }: { onOpen: (id: string) => void }) {
  const [list, setList] = useState<SessionSummary[]>([])

  useEffect(() => {
    let alive = true
    api
      .listSessions()
      .then((all) => {
        if (!alive) return
        // Сессии без загруженных файлов открывать незачем
        const shown = all
          .filter((s) => s.status !== 'idle')
          .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
        setList(shown.slice(0, LIMIT))
      })
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [])

  if (list.length === 0) return null
  return (
    <section className="mt-12">
      <h2 className="text-[19px] leading-7 font-semibold">Ранее загруженные</h2>
      <ul className="mt-4 divide-y divide-line overflow-hidden rounded-[var(--radius-card)] border border-line bg-surface">
        {list.map((s) => {
          const state = STATE[s.status]
          return (
            <li key={s.session_id}>
              <button
                type="button"
                onClick={() => onOpen(s.session_id)}
                className="flex w-full cursor-pointer items-center gap-4 px-6 py-4 text-left transition-colors hover:bg-subtle"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{s.meeting_title}</span>
                  <span className="text-sm text-ink-3">{s.meeting_date}</span>
                </span>
                {state && <span className={cx('text-sm', state.className)}>{state.text}</span>}
                <CaretRightIcon size={16} className="text-ink-3" />
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
