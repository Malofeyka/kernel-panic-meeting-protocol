import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { locateAction } from '@/lib/protocol'
import { mockApi } from '.'
import { parseFeedbackDate } from './protocol'

/** Mock отвечает с задержкой — прокручиваем фальшивые таймеры */
async function call<T>(p: Promise<T>): Promise<T> {
  const settled = p.then(
    (v) => ({ ok: true as const, v }),
    (e: unknown) => ({ ok: false as const, e }),
  )
  await vi.advanceTimersByTimeAsync(2000)
  const r = await settled
  if (!r.ok) throw r.e
  return r.v
}

async function readySession(audioName = 'meeting.wav') {
  const { session_id } = await call(
    mockApi.createSession({ meeting_title: 'Аппаратное совещание', meeting_date: '20.10.2026' }),
  )
  await call(mockApi.uploadFiles(session_id, { audio: new File(['x'], audioName) }))
  return session_id
}

describe('mockApi', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 21, 12))
  })
  afterEach(() => vi.useRealTimers())

  it('проходит обработку до готового проекта', async () => {
    const id = await readySession()
    expect((await call(mockApi.getStatus(id))).status).toBe('transcribing')
    await vi.advanceTimersByTimeAsync(20_000)
    expect(await call(mockApi.getStatus(id))).toMatchObject({
      status: 'ready',
      progress_percent: 100,
    })

    const details = await call(mockApi.getSession(id))
    expect(details).toMatchObject({ has_draft: true, files: { audio: 'meeting.wav' } })

    const draft = await call(mockApi.getDraft(id))
    expect(draft.agenda_items).toHaveLength(2)
    expect(draft.analytics.gaps.map((g) => g.type)).toEqual([
      'MISSING_DUE_DATE',
      'MISSING_DUE_DATE',
      'MISSING_ASSIGNEE',
    ])
    const transcript = await call(mockApi.getTranscript(id))
    const quote = draft.agenda_items[0]!.action_items[1]!.quote!
    expect(transcript.segments.some((s) => s.text === quote)).toBe(true)
  })

  it('ручное сохранение пересчитывает статус и аналитику', async () => {
    const id = await readySession()
    await vi.advanceTimersByTimeAsync(20_000)
    const draft = await call(mockApi.getDraft(id))
    const action = draft.agenda_items[0]!.action_items[1]!
    action.due_date = '30.11.2026'

    const r = await call(
      mockApi.refine(id, { action: 'manual_save', updated_agenda_items: draft.agenda_items }),
    )
    expect(locateAction(r.updated_draft, action.id!)?.action.status).toBe('valid')
    expect(r.updated_draft.analytics.gaps.some((g) => g.action_item_id === action.id)).toBe(false)
    expect(r.revision_cycle.current_cycle).toBe(0)
  })

  it('ИИ-правка: круг, итог в статусе и лимит в два круга', async () => {
    const id = await readySession()
    await vi.advanceTimersByTimeAsync(20_000)

    await expect(call(mockApi.refine(id, { action: 'ai_regenerate' }))).rejects.toMatchObject({
      status: 400,
    })

    const feedback = 'По переносу сроков ответственный Морозов, срок до 20 ноября'
    const r = await call(mockApi.refine(id, { action: 'ai_regenerate', user_feedback: feedback }))
    expect(r).toMatchObject({ status: 'refining', revision_cycle: { current_cycle: 1 } })
    await vi.advanceTimersByTimeAsync(5000)
    const st = await call(mockApi.getStatus(id))
    expect(st.status).toBe('ready')
    expect(st.current_step_description).toMatch(/круг 1 из 2.*п\. 2\.3: обновлено/)

    const draft = await call(mockApi.getDraft(id))
    expect(draft.agenda_items[1]!.action_items[0]).toMatchObject({
      assignee: 'Морозов Д.А.',
      due_date: '20.11.2026',
      status: 'valid',
    })

    await call(mockApi.refine(id, { action: 'ai_regenerate', user_feedback: 'Проверь сроки' }))
    await vi.advanceTimersByTimeAsync(5000)
    const second = await call(mockApi.getDraft(id))
    expect(second.revision_cycle).toMatchObject({ current_cycle: 2, is_escalated_to_manual: true })

    await expect(
      call(mockApi.refine(id, { action: 'ai_regenerate', user_feedback: 'Ещё раз' })),
    ).rejects.toMatchObject({ status: 400 })
  })

  it('ошибка обработки и повторный запуск', async () => {
    const id = await readySession('fail-запись.mp3')
    await vi.advanceTimersByTimeAsync(10_000)
    const failed = await call(mockApi.getStatus(id))
    expect(failed.status).toBe('failed')
    expect(failed.error_message).toBeTruthy()

    await call(mockApi.restartProcessing(id))
    await vi.advanceTimersByTimeAsync(20_000)
    expect((await call(mockApi.getStatus(id))).status).toBe('ready')
  })

  it('стенограмма вместо записи', async () => {
    const { session_id } = await call(mockApi.createSession({}))
    await call(mockApi.uploadFiles(session_id, { transcript: new File(['x'], 'стенограмма.txt') }))
    expect((await call(mockApi.getStatus(session_id))).current_step_description).toMatch(
      /Разбор стенограммы/,
    )
  })

  it('загрузка сообщает прогресс и отменяется', async () => {
    const { session_id } = await call(mockApi.createSession({ meeting_title: 'Тест' }))
    const progress: number[] = []
    const ctrl = new AbortController()
    const settled = mockApi
      .uploadFiles(
        session_id,
        { audio: new File([new Uint8Array(1000)], 'meeting.wav') },
        { signal: ctrl.signal, onProgress: (p) => progress.push(p.loaded) },
      )
      .catch((e: unknown) => e)
    await vi.advanceTimersByTimeAsync(500)
    ctrl.abort()
    const err = await settled
    expect(progress.length).toBeGreaterThan(0)
    expect((err as DOMException).name).toBe('AbortError')
  })

  it('неизвестная сессия — 404', async () => {
    await expect(call(mockApi.getStatus('nope'))).rejects.toMatchObject({ status: 404 })
  })
})

describe('parseFeedbackDate', () => {
  it.each([
    ['до 20 ноября', '20.11.2026'],
    ['к 01.12', '01.12.2026'],
    ['срок 15.01.2027', '15.01.2027'],
    ['до 5 сентября', '05.09.2027'],
    ['без срока', null],
  ])('%s → %s', (text, expected) => {
    expect(parseFeedbackDate(text, '20.10.2026')).toBe(expected)
  })
})
