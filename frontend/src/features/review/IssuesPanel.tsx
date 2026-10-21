import type { AnalyticsReport, ProtocolDraft, Severity } from '@/api'
import { locateAction } from '@/lib/protocol'

export interface IssueTarget {
  actionId: string | null
  agendaItem: number | null
  quote: string | null
  start: number | null
}

interface Issue extends IssueTarget {
  key: string
  text: string
  note: string | null
  severity: Severity
}

const RANK: Record<Severity, number> = { high: 0, medium: 1, low: 2 }
const DATE_GAPS = new Set(['MISSING_DUE_DATE', 'VAGUE_DUE_DATE'])

/**
 * Замечания аналитики (UI-04). Сервер пересчитывает их при сохранении; до этого
 * скрываем то, что секретарь уже исправил в документе: заполнил срок, назначил исполнителя,
 * удалил пункт.
 */
export function collectIssues(analytics: AnalyticsReport, draft: ProtocolDraft) {
  const exists = (id: string) => locateAction(draft, id) !== null
  const sort = (list: Issue[]) => list.sort((a, b) => RANK[a.severity] - RANK[b.severity])

  const gaps = analytics.gaps
    .filter((g) => {
      if (!g.action_item_id) return true
      const found = locateAction(draft, g.action_item_id)
      if (!found) return false
      if (DATE_GAPS.has(g.type) && found.action.due_date) return false
      if (g.type === 'MISSING_ASSIGNEE' && found.action.assignee) return false
      return true
    })
    .map((g, i): Issue => ({
      key: `gap-${i}`,
      text: g.description,
      note: null,
      severity: g.severity,
      actionId: g.action_item_id,
      agendaItem: g.agenda_item_number,
      quote: g.context_quote,
      start: g.source_start,
    }))

  const contradictions = analytics.contradictions
    .filter((c) => c.action_item_ids.length === 0 || c.action_item_ids.some(exists))
    .map((c): Issue => ({
      key: c.id,
      text: c.description,
      note: c.archive_reference,
      severity: 'high',
      actionId: c.action_item_ids.find(exists) ?? null,
      agendaItem: null,
      quote: c.quotes[0] ?? null,
      start: null,
    }))

  const risks = analytics.risks
    .filter((r) => r.action_item_ids.length === 0 || r.action_item_ids.some(exists))
    .map((r): Issue => ({
      key: r.id,
      text: r.description,
      note: r.archive_reference,
      severity: r.severity,
      actionId: r.action_item_ids.find(exists) ?? null,
      agendaItem: null,
      quote: null,
      start: null,
    }))

  return [
    { title: 'Пробелы', items: sort(gaps) },
    { title: 'Противоречия', items: sort(contradictions) },
    { title: 'Риски', items: sort(risks) },
  ].filter((g) => g.items.length > 0)
}

export function IssuesPanel({
  analytics,
  draft,
  onPick,
}: {
  analytics: AnalyticsReport
  draft: ProtocolDraft
  onPick: (t: IssueTarget) => void
}) {
  const groups = collectIssues(analytics, draft)
  if (groups.length === 0) {
    return (
      <p className="px-5 py-4 text-ink-2">
        Замечаний нет. Проверьте текст протокола и скачайте документ.
      </p>
    )
  }
  return (
    <div className="flex flex-col gap-5 py-4">
      {groups.map((g) => (
        <section key={g.title}>
          <h3 className="px-5 text-sm font-semibold tracking-[0.06em] text-ink-2 uppercase">
            {g.title}
          </h3>
          <ul className="mt-1">
            {g.items.map((it) => (
              <li key={it.key}>
                <button
                  type="button"
                  onClick={() => onPick(it)}
                  className="w-full cursor-pointer px-5 py-2.5 text-left transition-colors hover:bg-subtle"
                >
                  <span className="block">{it.text}</span>
                  {it.note && <span className="mt-0.5 block text-sm text-ink-3">{it.note}</span>}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}
