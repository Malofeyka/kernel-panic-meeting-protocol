import { useState } from 'react'
import type { RevisionCycleState } from '@/api'
import { AutoTextarea } from '@/ui/AutoTextarea'
import { Button } from '@/ui/Button'
import { controlClass } from '@/ui/Field'
import { cx } from '@/lib/cx'

interface Props {
  cycle: RevisionCycleState
  refining: boolean
  error: string | null
  /** true — замечание принято, поле можно очистить */
  onSubmit: (feedback: string) => Promise<boolean>
}

/**
 * Доработка через ИИ (UI-03): не больше max_cycles кругов. После лимита — только ручная правка.
 * Несохранённые правки уходят вместе с замечанием, ИИ работает поверх них.
 */
export function RefinePanel({ cycle, refining, error, onSubmit }: Props) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const used = cycle.current_cycle
  const left = cycle.max_cycles - used

  if (cycle.is_escalated_to_manual && !refining) {
    return (
      <div className="px-5 py-4">
        <p className="font-medium">Доработка через ИИ больше недоступна</p>
        <p className="mt-1 text-ink-2">
          Лимит кругов исчерпан. Исправьте оставшееся в документе вручную и скачайте протокол.
        </p>
      </div>
    )
  }

  const submit = async () => {
    if (!text.trim() || sending) return
    setSending(true)
    if (await onSubmit(text.trim())) setText('')
    setSending(false)
  }

  return (
    <div className="px-5 py-4">
      <div className="flex items-baseline justify-between gap-3">
        <p className="font-medium">Доработка через ИИ</p>
        <p className="text-sm text-ink-3">
          {used === 0 ? `Доступно кругов: ${left}` : `Круг ${used} из ${cycle.max_cycles}`}
        </p>
      </div>
      <AutoTextarea
        aria-label="Замечание для ИИ"
        placeholder="Что исправить? Например: по переносу сроков с подрядчиками ответственный Морозов, срок до 20 ноября"
        className={cx(controlClass, 'mt-3 h-auto max-h-48 min-h-[88px] py-2.5 leading-6')}
        value={text}
        disabled={refining || sending}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void submit()
        }}
      />
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
      <Button
        className="mt-3 w-full"
        loading={refining || sending}
        disabled={!text.trim()}
        onClick={() => void submit()}
      >
        {refining ? 'ИИ вносит правки…' : 'Отправить на доработку'}
      </Button>
    </div>
  )
}
