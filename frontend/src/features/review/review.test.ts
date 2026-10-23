import { describe, expect, it } from 'vitest'
import { demoDraft, demoTranscript } from '@/api/mock/fixtures'
import { normalize } from '@/api/mock/protocol'
import { actionNumber, shortName } from '@/lib/protocol'
import { editorReducer, prepareForSave } from './draftReducer'
import { collectIssues } from './IssuesPanel'
import { findSegment } from './TranscriptPanel'

const transcript = demoTranscript('meeting.wav')
const draft = () => normalize(demoDraft('s1', 'Аппаратное совещание', '20.10.2026', transcript), [])

describe('редактор проекта', () => {
  it('правка срока пересчитывает статус и помечает документ изменённым', () => {
    const s = editorReducer(
      { draft: draft(), dirty: false },
      { type: 'action', item: 0, index: 1, patch: { due_date: '30.11.2026' } },
    )
    expect(s.dirty).toBe(true)
    expect(s.draft.agenda_items[0]!.action_items[1]!.status).toBe('valid')
  })

  it('ответственный из списка участников получает должность', () => {
    const s = editorReducer(
      { draft: draft(), dirty: false },
      { type: 'action', item: 1, index: 0, patch: { assignee: 'Морозов Д.А.' } },
    )
    expect(s.draft.agenda_items[1]!.action_items[0]).toMatchObject({
      assignee_role: 'Начальник отдела инфраструктуры',
      status: 'missing_date',
    })
  })

  it('нумерация как в документе: поручения продолжают решения', () => {
    const d = draft()
    expect(actionNumber(d.agenda_items[1]!, 0)).toBe('2.3')
  })

  it('новые пустые пункты отбрасываются, стёртая тема — ошибка', () => {
    let s = editorReducer({ draft: draft(), dirty: false }, { type: 'actionAdd', item: 0 })
    s = editorReducer(s, { type: 'itemAdd' })
    const ok = prepareForSave(s.draft)
    expect(ok.ok && ok.draft.agenda_items).toHaveLength(2)
    expect(ok.ok && ok.draft.agenda_items[0]!.action_items).toHaveLength(2)

    s = editorReducer(s, { type: 'item', item: 0, patch: { topic: ' ' } })
    expect(prepareForSave(s.draft)).toMatchObject({ ok: false, target: 'item-1' })
  })

  it('участник добавляется с кратким ФИО', () => {
    const s = editorReducer(
      { draft: draft(), dirty: false },
      { type: 'attendeeAdd', name: 'Смирнова  Ольга Петровна' },
    )
    expect(s.draft.metadata.attendees.at(-1)).toMatchObject({
      full_name: 'Смирнова Ольга Петровна',
      short_name: 'Смирнова О.П.',
    })
    expect(shortName('ГКУ «Центр»')).toBe('ГКУ «Центр»')
  })
})

describe('замечания', () => {
  it('исправленное в документе до сохранения скрывается', () => {
    const d = draft()
    const before = collectIssues(d.analytics, d).find((g) => g.title === 'Пробелы')!
    expect(before.items).toHaveLength(3)

    const s = editorReducer(
      { draft: d, dirty: false },
      { type: 'action', item: 1, index: 0, patch: { assignee: 'Морозов Д.А.' } },
    )
    const after = collectIssues(d.analytics, s.draft).find((g) => g.title === 'Пробелы')!
    expect(after.items.map((i) => i.text)).toEqual([
      expect.stringContaining('п. 1.3'),
      expect.stringContaining('п. 2.3'),
    ])
  })

  it('цитата находится в стенограмме', () => {
    const quote = draft().agenda_items[1]!.action_items[0]!.quote!
    const i = findSegment(transcript.segments, quote, null)
    expect(transcript.segments[i]!.text).toBe(quote)
  })
})
