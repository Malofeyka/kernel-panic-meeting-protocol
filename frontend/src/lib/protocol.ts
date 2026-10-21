import type { ActionItem, ActionItemStatus, AgendaItem, ProtocolDraft } from '@/api/types'

/**
 * Нумерация как в итоговом .docx (backend: ProtocolDraft.iter_action_items):
 * сначала решения 1.1, 1.2, затем поручения продолжают счёт — 1.3, 1.4.
 */
export const decisionNumber = (item: AgendaItem, index: number) =>
  `${item.item_number}.${index + 1}`

export const actionNumber = (item: AgendaItem, index: number) =>
  `${item.item_number}.${item.decisions.length + index + 1}`

/** Как статус считает сервер (protocol.py, ActionItem._compute_status) */
export function actionStatus(a: Pick<ActionItem, 'assignee' | 'due_date' | 'is_recurring'>) {
  const hasDate = !!a.due_date || a.is_recurring
  const hasAssignee = !!a.assignee?.trim()
  const status: ActionItemStatus =
    hasDate && hasAssignee
      ? 'valid'
      : hasAssignee
        ? 'missing_date'
        : hasDate
          ? 'missing_assignee'
          : 'missing_assignee_and_date'
  return status
}

/** «Иванов Игорь Иванович» → «Иванов И.И.»; уже краткое или одно слово — как есть */
export function shortName(full: string): string {
  const parts = full.trim().split(/\s+/)
  const isName =
    parts.length >= 2 && parts.length <= 3 && parts.every((p) => /^[А-ЯЁ][а-яё-]+$/.test(p))
  if (!isName) return full.trim()
  const [last, ...rest] = parts
  return `${last} ${rest.map((p) => `${p[0]?.toUpperCase()}.`).join('')}`
}

/** Найти поручение и его номер по id */
export function locateAction(draft: ProtocolDraft, id: string) {
  for (const item of draft.agenda_items) {
    const i = item.action_items.findIndex((a) => a.id === id)
    if (i >= 0)
      return { item, index: i, action: item.action_items[i]!, label: actionNumber(item, i) }
  }
  return null
}

export const emptyAction = (): ActionItem => ({
  task: '',
  assignee: null,
  assignee_role: null,
  assignee_raw: null,
  due_date: null,
  due_date_raw: null,
  is_recurring: false,
  status: 'missing_assignee_and_date',
  quote: null,
  source_start: null,
  source_end: null,
  origin: 'manual',
})
