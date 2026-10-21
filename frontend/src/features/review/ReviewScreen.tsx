import type { ProtocolDraft, SessionStatusResponse } from '@/api'
import { ruLongDate } from '@/lib/dates'
import { Notice } from '@/ui/Notice'

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

/** Экран проверки проекта. Редактор, замечания и доработка через ИИ — FE-201..FE-204 */
export function ReviewScreen({ draft }: Props) {
  return (
    <>
      <h1 className="text-[32px] leading-10 font-semibold tracking-[-0.01em]">
        {draft.metadata.meeting_title}
      </h1>
      <p className="mt-1 text-[17px] text-ink-2">{ruLongDate(draft.metadata.meeting_date)}</p>
      <Notice tone="success" className="mt-8" title="Проект протокола готов" />
    </>
  )
}
