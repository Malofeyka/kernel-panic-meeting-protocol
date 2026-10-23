import type { ActionItem, AgendaItem, ProtocolDraft, ProtocolMetadata } from '@/api'
import { actionStatus, emptyAction, shortName } from '@/lib/protocol'

/**
 * Локальная копия проекта, которую правит секретарь. На сервер уходит целиком
 * при «Сохранить», ИИ-правке или экспорте (POST /refine).
 */
export interface EditorState {
  draft: ProtocolDraft
  dirty: boolean
}

type Meta = Partial<Omit<ProtocolMetadata, 'attendees'>>

export type EditorAction =
  | { type: 'reset'; draft: ProtocolDraft }
  | { type: 'meta'; patch: Meta }
  | { type: 'attendeeAdd'; name: string }
  | { type: 'attendeeRemove'; index: number }
  | { type: 'item'; item: number; patch: Partial<Pick<AgendaItem, 'topic' | 'reporter'>> }
  | { type: 'itemAdd' }
  | { type: 'itemRemove'; item: number }
  | { type: 'decision'; item: number; index: number; text: string }
  | { type: 'decisionAdd'; item: number }
  | { type: 'decisionRemove'; item: number; index: number }
  | { type: 'action'; item: number; index: number; patch: Partial<ActionItem> }
  | { type: 'actionAdd'; item: number }
  | { type: 'actionRemove'; item: number; index: number }

/** id для нового пункта: сервер принимает свой, а интерфейсу он нужен сразу (ключи, подсветка) */
export const newId = (prefix: 'act' | 'dec') =>
  `${prefix}-${crypto.randomUUID().replaceAll('-', '').slice(0, 8)}`

const withItem = (
  d: ProtocolDraft,
  index: number,
  fn: (item: AgendaItem) => AgendaItem,
): ProtocolDraft => ({
  ...d,
  agenda_items: d.agenda_items.map((it, i) => (i === index ? fn(it) : it)),
})

const without = <T>(list: T[], index: number) => list.filter((_, i) => i !== index)

function edit(d: ProtocolDraft, a: Exclude<EditorAction, { type: 'reset' }>): ProtocolDraft {
  switch (a.type) {
    case 'meta':
      return { ...d, metadata: { ...d.metadata, ...a.patch } }
    case 'attendeeAdd': {
      const name = a.name.trim().replace(/\s+/g, ' ')
      if (!name) return d
      const known = d.metadata.attendees.some((p) => p.full_name === name || p.short_name === name)
      if (known) return d
      const attendee = { full_name: name, short_name: shortName(name), position: null }
      return { ...d, metadata: { ...d.metadata, attendees: [...d.metadata.attendees, attendee] } }
    }
    case 'attendeeRemove':
      return {
        ...d,
        metadata: { ...d.metadata, attendees: without(d.metadata.attendees, a.index) },
      }
    case 'item':
      return withItem(d, a.item, (it) => ({ ...it, ...a.patch }))
    case 'itemAdd':
      return {
        ...d,
        agenda_items: [
          ...d.agenda_items,
          {
            item_number: d.agenda_items.length + 1,
            topic: '',
            reporter: null,
            decisions: [],
            action_items: [],
          },
        ],
      }
    case 'itemRemove':
      return {
        ...d,
        agenda_items: without(d.agenda_items, a.item).map((it, i) => ({
          ...it,
          item_number: i + 1,
        })),
      }
    case 'decision':
      return withItem(d, a.item, (it) => ({
        ...it,
        decisions: it.decisions.map((x, i) =>
          i === a.index ? { ...x, text: a.text, origin: 'manual' } : x,
        ),
      }))
    case 'decisionAdd':
      return withItem(d, a.item, (it) => ({
        ...it,
        decisions: [
          ...it.decisions,
          {
            id: newId('dec'),
            text: '',
            quote: null,
            source_start: null,
            source_end: null,
            origin: 'manual',
          },
        ],
      }))
    case 'decisionRemove':
      return withItem(d, a.item, (it) => ({ ...it, decisions: without(it.decisions, a.index) }))
    case 'action':
      return withItem(d, a.item, (it) => ({
        ...it,
        action_items: it.action_items.map((x, i) => {
          if (i !== a.index) return x
          const next = { ...x, ...a.patch }
          if ('task' in a.patch) next.origin = 'manual'
          if ('assignee' in a.patch) {
            // Должность подставляем, только если выбран участник из списка
            const who = d.metadata.attendees.find(
              (p) => p.short_name === next.assignee || p.full_name === next.assignee,
            )
            next.assignee_role = who?.position ?? null
          }
          return { ...next, status: actionStatus(next) }
        }),
      }))
    case 'actionAdd':
      return withItem(d, a.item, (it) => ({
        ...it,
        action_items: [...it.action_items, { ...emptyAction(), id: newId('act') }],
      }))
    case 'actionRemove':
      return withItem(d, a.item, (it) => ({
        ...it,
        action_items: without(it.action_items, a.index),
      }))
  }
}

export function editorReducer(state: EditorState, action: EditorAction): EditorState {
  if (action.type === 'reset') return { draft: action.draft, dirty: false }
  return { draft: edit(state.draft, action), dirty: true }
}

/**
 * Проверка перед отправкой: сервер не примет пустой текст (422).
 * Пустые новые пункты просто отбрасываем, а заполненные раньше и стёртые — просим исправить.
 */
export function prepareForSave(
  draft: ProtocolDraft,
): { ok: true; draft: ProtocolDraft } | { ok: false; message: string; target: string } {
  const items: AgendaItem[] = []
  for (const [i, it] of draft.agenda_items.entries()) {
    const decisions = it.decisions.filter((x) => x.text.trim())
    const actions = it.action_items.filter((x) => x.task.trim())
    if (!it.topic.trim()) {
      if (decisions.length === 0 && actions.length === 0 && !it.reporter) continue
      return {
        ok: false,
        message: `Укажите тему вопроса ${i + 1} или удалите его.`,
        target: `item-${i + 1}`,
      }
    }
    items.push({
      ...it,
      item_number: items.length + 1,
      topic: it.topic.trim(),
      decisions: decisions.map((x) => ({ ...x, text: x.text.trim() })),
      action_items: actions.map((x) => ({ ...x, task: x.task.trim() })),
    })
  }
  if (!draft.metadata.meeting_title.trim()) {
    return { ok: false, message: 'Укажите наименование совещания.', target: 'meta-title' }
  }
  return { ok: true, draft: { ...draft, agenda_items: items } }
}
