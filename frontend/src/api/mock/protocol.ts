import { actionNumber, actionStatus } from '@/lib/protocol'
import type { AnalyticsReport, GapIssue, ProtocolDraft, Risk } from '../types'

/** Упрощённая копия серверной аналитики (backend/app/services/analytics.py) для mock-режима */

const parseRu = (s: string) => {
  const [d, m, y] = s.split('.').map(Number)
  return new Date(y!, m! - 1, d!)
}

let seq = 0
const newId = (prefix: string) =>
  `${prefix}-${Date.now().toString(16).slice(-5)}${(++seq).toString(16).padStart(3, '0')}`

/** Пересчёт статусов, присвоение id новым пунктам и аналитика — как при сохранении на сервере */
export function normalize(draft: ProtocolDraft, archive: string[]): ProtocolDraft {
  const items = draft.agenda_items.map((item, i) => ({
    ...item,
    item_number: i + 1,
    decisions: item.decisions.map((d) => ({ ...d, id: d.id ?? newId('dec') })),
    action_items: item.action_items.map((a) => ({
      ...a,
      id: a.id ?? newId('act'),
      assignee: a.assignee?.trim() || null,
      status: actionStatus(a),
    })),
  }))
  const next = { ...draft, agenda_items: items }
  return { ...next, analytics: analyze(next, archive) }
}

export function analyze(draft: ProtocolDraft, archive: string[]): AnalyticsReport {
  const gaps: GapIssue[] = []
  const risks: Risk[] = []
  const meeting = parseRu(draft.metadata.meeting_date)

  for (const item of draft.agenda_items) {
    if (item.decisions.length === 0 && item.action_items.length === 0) {
      gaps.push({
        type: 'NO_DECISION_FOR_AGENDA_ITEM',
        severity: 'medium',
        description: `Вопрос ${item.item_number}: не зафиксировано ни решения, ни поручения.`,
        agenda_item_number: item.item_number,
        action_item_id: null,
        context_quote: null,
        source_start: null,
      })
    }
    item.action_items.forEach((a, i) => {
      const label = `п. ${actionNumber(item, i)}`
      const base = {
        severity: 'high' as const,
        agenda_item_number: item.item_number,
        action_item_id: a.id ?? null,
        context_quote: a.quote,
        source_start: a.source_start,
      }
      if (!a.due_date && !a.is_recurring) {
        const heard = a.due_date_raw ? ` (прозвучало: «${a.due_date_raw}»)` : ''
        gaps.push({
          ...base,
          type: 'MISSING_DUE_DATE',
          description: `${label}: поручение «${a.task}» не содержит срока исполнения${heard}.`,
        })
      }
      if (!a.assignee) {
        gaps.push({
          ...base,
          type: 'MISSING_ASSIGNEE',
          description: `${label}: для поручения «${a.task}» не назван ответственный исполнитель.`,
        })
      }
      if (a.due_date) {
        const due = parseRu(a.due_date)
        if (due < meeting) {
          risks.push({
            id: newId('risk'),
            type: 'DEADLINE_IN_PAST',
            severity: 'high',
            description: `${label}: срок ${a.due_date} раньше даты совещания.`,
            action_item_ids: [a.id!],
            archive_reference: null,
          })
        } else if (due.getDay() === 0 || due.getDay() === 6) {
          risks.push({
            id: newId('risk'),
            type: 'WEEKEND_DEADLINE',
            severity: 'low',
            description: `${label}: срок ${a.due_date} приходится на выходной день.`,
            action_item_ids: [a.id!],
            archive_reference: null,
          })
        }
      }
      // Демо-сверка с архивом: в протоколе от 18.08.2026 было похожее поручение
      if (
        archive.some((n) => n.includes('18.08.2026')) &&
        /пунктов проведения экзаменов/.test(a.task)
      ) {
        risks.push({
          id: newId('risk'),
          type: 'REPEATED_ASSIGNMENT',
          severity: 'medium',
          description: `${label}: похожее поручение уже давалось — «Направить предложения по составу пунктов проведения экзаменов» (Сидоров С.С., до 30.09.2026). Проверьте, выполнено ли оно.`,
          action_item_ids: [a.id!],
          archive_reference: 'Протокол от 18.08.2026, п. 1.2',
        })
      }
    })
  }
  return { gaps, contradictions: [], risks }
}

const MONTHS = [
  'январ',
  'феврал',
  'март',
  'апрел',
  'ма',
  'июн',
  'июл',
  'август',
  'сентябр',
  'октябр',
  'ноябр',
  'декабр',
]

/** «до 20 ноября», «к 01.12», «20.11.2026» → ДД.ММ.ГГГГ относительно даты совещания */
export function parseFeedbackDate(text: string, meetingDate: string): string | null {
  const meeting = parseRu(meetingDate)
  let d: number | undefined, m: number | undefined, y: number | undefined
  const num = /(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?/.exec(text)
  if (num) {
    d = Number(num[1])
    m = Number(num[2])
    y = num[3] ? Number(num[3]) : undefined
  } else {
    const word = /(\d{1,2})\s+([а-яё]+)/i.exec(text)
    const idx = word ? MONTHS.findIndex((p) => word[2]!.toLowerCase().startsWith(p)) : -1
    if (word && idx >= 0) {
      d = Number(word[1])
      m = idx + 1
    }
  }
  if (!d || !m || m > 12 || d > 31) return null
  let year = y ?? meeting.getFullYear()
  if (!y && new Date(year, m - 1, d) < meeting) year++
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d)}.${pad(m)}.${year}`
}

/** Имитация ИИ-правки: дополняет первое неполное поручение сроком/исполнителем из замечания */
export function applyFeedback(
  draft: ProtocolDraft,
  feedback: string,
): { draft: ProtocolDraft; summary: string } {
  const due = parseFeedbackDate(feedback, draft.metadata.meeting_date)
  const lower = feedback.toLowerCase()
  const person = draft.metadata.attendees.find((p) => {
    const surname = p.full_name.split(' ')[0]!.toLowerCase()
    return lower.includes(surname.slice(0, Math.max(4, surname.length - 2)))
  })

  // Какое поручение имеется в виду: больше всего общих слов с замечанием
  const stems = (t: string) =>
    new Set((t.toLowerCase().match(/[а-яё]{5,}/g) ?? []).map((w) => w.slice(0, 5)))
  const wanted = stems(feedback)
  let target: { item: number; index: number; score: number } | null = null
  draft.agenda_items.forEach((item, ii) =>
    item.action_items.forEach((a, i) => {
      const canFill = (!a.due_date && due) || (!a.assignee && person)
      if (!canFill) return
      const score = [...stems(a.task)].filter((w) => wanted.has(w)).length
      if (!target || score > target.score) target = { item: ii, index: i, score }
    }),
  )

  const changes: string[] = []
  const pick = target as { item: number; index: number } | null
  const items = draft.agenda_items.map((item, ii) => ({
    ...item,
    action_items: item.action_items.map((a, i) => {
      if (!pick || pick.item !== ii || pick.index !== i) return a
      const needDate = !a.due_date && due
      const needWho = !a.assignee && person
      const what = [needWho && 'ответственный', needDate && 'срок'].filter(Boolean).join(', ')
      changes.push(`п. ${actionNumber(item, i)}: обновлено (${what})`)
      return {
        ...a,
        due_date: needDate ? due : a.due_date,
        assignee: needWho ? person.short_name : a.assignee,
        assignee_role: needWho ? person.position : a.assignee_role,
      }
    }),
  }))
  return {
    draft: { ...draft, agenda_items: items },
    summary: changes.length ? changes.join('; ') : 'изменений не внесено',
  }
}
