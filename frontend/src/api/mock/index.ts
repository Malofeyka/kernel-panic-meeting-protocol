import type { ApiClient } from '../client'
import { ApiError } from '../errors'
import type {
  ProcessingStep,
  ProtocolDraft,
  SessionDetails,
  SessionStatusResponse,
  UploadedFilesInfo,
} from '../types'
import { demoDraft, demoTranscript } from './fixtures'
import { applyFeedback, normalize } from './protocol'

/**
 * Имитация бэкенда (VITE_USE_MOCKS=1) по контракту docs/api/frontend_integration.md.
 * Статус считается от времени загрузки, сессии хранятся в localStorage и переживают
 * перезагрузку страницы. Аудиофайл с «fail» в имени — ошибка распознавания
 * («Повторить» после неё проходит успешно).
 */

interface MockSession {
  id: string
  title: string
  date: string
  createdAt: number
  updatedAt: number
  uploadedAt: number | null
  files: UploadedFilesInfo
  fail: boolean
  /** Сохранённый проект; null — ещё не сформирован */
  draft: ProtocolDraft | null
  refine: { startedAt: number; feedback: string } | null
  /** Итог последней ИИ-правки — показывается в current_step_description */
  message: string | null
}

const KEY = 'kp-mock-sessions-v2'
const speed = () => Math.max(0.1, Number(import.meta.env.VITE_MOCK_SPEED ?? 1) || 1)
const REFINE_SEC = 4
const FAIL_AT = 4

/** Таймлайн обработки: [начало (с), шаг, процент в начале, процент в конце, описание] */
const TIMELINE: [number, ProcessingStep, number, number, string][] = [
  [0, 'transcribing', 5, 45, 'Распознавание речи'],
  [6, 'extracting', 50, 75, 'Извлечение решений, поручений, сроков и ответственных'],
  [13, 'cross_checking', 80, 95, 'Сверка с повесткой, списком участников и архивом протоколов'],
  [18, 'ready', 100, 100, 'Проект протокола готов к вычитке'],
]

function load(): Record<string, MockSession> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '{}') as Record<string, MockSession>
  } catch {
    return {}
  }
}

function save() {
  try {
    localStorage.setItem(KEY, JSON.stringify(db()))
  } catch {
    // Хранилище недоступно (приватный режим) — сессия проживёт до перезагрузки
  }
}

// Лениво: без побочных эффектов при импорте модуль вырезается из прод-сборки
let cache: Record<string, MockSession> | null = null
const db = () => (cache ??= load())

const wait = (min = 150, max = 450) =>
  new Promise((r) => setTimeout(r, (min + Math.random() * (max - min)) / Math.sqrt(speed())))

const iso = (ms = Date.now()) => new Date(ms).toISOString()
const elapsed = (from: number) => ((Date.now() - from) / 1000) * speed()
const sourceName = (s: MockSession) => s.files.audio ?? s.files.transcript ?? ''

function find(id: string): MockSession {
  const s = db()[id]
  if (!s) throw new ApiError(404, 'Сессия не найдена')
  advance(s)
  return s
}

/** Доводит сессию до текущего момента: формирует проект, завершает ИИ-правку */
function advance(s: MockSession) {
  if (s.uploadedAt === null) return
  if (!s.draft && !s.fail && elapsed(s.uploadedAt) >= TIMELINE.at(-1)![0]) {
    const transcript = demoTranscript(sourceName(s))
    s.draft = normalize(demoDraft(s.id, s.title, s.date, transcript), s.files.archive)
    s.updatedAt = Date.now()
    save()
  }
  if (s.draft && s.refine && elapsed(s.refine.startedAt) >= REFINE_SEC) {
    const { current_cycle: n, max_cycles: max } = s.draft.revision_cycle
    const { draft, summary } = applyFeedback(s.draft, s.refine.feedback)
    s.draft = normalize(draft, s.files.archive)
    const limit = n >= max ? ' Лимит ИИ-правок исчерпан — дальнейшие правки вносятся вручную.' : ''
    s.message = `ИИ-правка выполнена (круг ${n} из ${max}): ${summary}.${limit}`
    s.refine = null
    s.updatedAt = Date.now()
    save()
  }
}

function status(s: MockSession): SessionStatusResponse {
  const base = { session_id: s.id, error_message: null, updated_at: iso(s.updatedAt) }
  if (s.uploadedAt === null) {
    return {
      ...base,
      status: 'idle',
      progress_percent: 0,
      current_step_description: 'Сессия создана. Ожидание загрузки файлов.',
    }
  }
  if (s.refine) {
    const { current_cycle: n, max_cycles: max } = s.draft!.revision_cycle
    return {
      ...base,
      status: 'refining',
      progress_percent: 50,
      current_step_description: `ИИ-агент вносит правки (круг ${n} из ${max})…`,
    }
  }
  if (s.draft) {
    return {
      ...base,
      status: 'ready',
      progress_percent: 100,
      current_step_description: s.message ?? 'Проект протокола готов к вычитке',
    }
  }
  const t = elapsed(s.uploadedAt)
  if (s.fail && t >= FAIL_AT) {
    return {
      ...base,
      status: 'failed',
      progress_percent: 30,
      current_step_description: 'Обработка остановлена из-за ошибки.',
      error_message:
        'Не удалось распознать речь: аудиодорожка пустая или повреждена. Проверьте файл и загрузите его снова.',
    }
  }
  let i = 0
  while (i + 1 < TIMELINE.length && t >= TIMELINE[i + 1]![0]) i++
  const [start, step, from, to, text] = TIMELINE[i]!
  const end = TIMELINE[i + 1]?.[0] ?? start
  const k = end > start ? Math.min(1, (t - start) / (end - start)) : 1
  const label =
    step === 'transcribing'
      ? s.files.transcript
        ? `Разбор стенограммы «${s.files.transcript}»`
        : `${text}: «${s.files.audio}»`
      : text
  return {
    ...base,
    status: step,
    progress_percent: Math.round(from + (to - from) * k),
    current_step_description: label,
  }
}

function details(s: MockSession): SessionDetails {
  const st = status(s)
  return {
    ...st,
    meeting_title: s.draft?.metadata.meeting_title ?? s.title,
    meeting_date: s.draft?.metadata.meeting_date ?? s.date,
    has_draft: s.draft !== null,
    has_transcript: s.draft !== null,
    files: s.files,
    export: null,
    input_warnings: [],
    created_at: iso(s.createdAt),
  }
}

function emptyDraft(s: MockSession): ProtocolDraft {
  return {
    session_id: s.id,
    metadata: {
      meeting_title: s.title,
      meeting_date: s.date,
      protocol_number: null,
      chairperson: null,
      secretary: null,
      attendees: [],
    },
    agenda_items: [],
    analytics: { gaps: [], contradictions: [], risks: [] },
    revision_cycle: { current_cycle: 0, max_cycles: 2, is_escalated_to_manual: false },
  }
}

function ensureIdle(s: MockSession) {
  const st = status(s).status
  if (!['idle', 'ready', 'failed'].includes(st))
    throw new ApiError(409, 'Сессия сейчас обрабатывается. Дождитесь завершения.')
}

/** Текстовая версия протокола вместо .docx: в mock-режиме генератора документов нет */
function renderText(d: ProtocolDraft): string {
  const m = d.metadata
  const lines = [
    'ПРОТОКОЛ',
    m.meeting_title,
    `${m.meeting_date} № ${m.protocol_number ?? '____'}`,
    '',
    `Председатель: ${m.chairperson ?? '[уточнить]'}`,
    `Секретарь: ${m.secretary ?? '[уточнить]'}`,
    `Присутствовали: ${m.attendees.map((a) => a.short_name).join(', ')}`,
  ]
  for (const item of d.agenda_items) {
    lines.push('', `${item.item_number}. ${item.topic}`)
    if (item.reporter) lines.push(`СЛУШАЛИ: ${item.reporter}`)
    lines.push('РЕШИЛИ:')
    item.decisions.forEach((x, i) => lines.push(`${item.item_number}.${i + 1}. ${x.text}.`))
    item.action_items.forEach((a, i) => {
      const n = item.decisions.length + i + 1
      lines.push(
        `${item.item_number}.${n}. ${a.task}. Срок: ${a.due_date ? `до ${a.due_date}` : '[уточнить]'}. Ответственный: ${a.assignee ?? '[уточнить]'}`,
      )
    })
  }
  return lines.join('\n')
}

export const mockApi: ApiClient = {
  async health() {
    await wait(50, 150)
    return {
      status: 'healthy',
      service: 'kernel-panic-meeting-protocol (mock)',
      isolated_mode: true,
      max_revision_cycles: 2,
    }
  },

  async listSessions() {
    await wait()
    return Object.values(db())
      .map((s) => {
        advance(s)
        return {
          session_id: s.id,
          meeting_title: s.draft?.metadata.meeting_title ?? s.title,
          meeting_date: s.draft?.metadata.meeting_date ?? s.date,
          status: status(s).status,
          created_at: iso(s.createdAt),
          updated_at: iso(s.updatedAt),
        }
      })
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  },

  async createSession(req) {
    await wait()
    const id = crypto.randomUUID()
    db()[id] = {
      id,
      title: req.meeting_title || 'Аппаратное совещание',
      date: req.meeting_date || new Date().toLocaleDateString('ru-RU'),
      createdAt: Date.now(),
      updatedAt: Date.now(),
      uploadedAt: null,
      files: {
        audio: null,
        transcript: null,
        agenda: null,
        attendees: null,
        template: null,
        archive: [],
      },
      fail: false,
      draft: null,
      refine: null,
      message: null,
    }
    save()
    return { session_id: id, status: 'idle', created_at: iso() }
  },

  async getSession(id) {
    await wait(80, 200)
    return details(find(id))
  },

  uploadFiles(id, files, { onProgress, signal } = {}) {
    const s = find(id)
    if (!files.audio && !files.transcript)
      return Promise.reject(
        new ApiError(400, 'Загрузите аудиозапись совещания или готовую стенограмму.'),
      )
    const list = [
      files.audio,
      files.transcript,
      files.agenda,
      files.attendees,
      files.template,
      ...(files.archive ?? []),
    ].filter((f): f is File => !!f)
    const total = list.reduce((sum, f) => sum + f.size, 0)
    // Локальная сеть быстрая, но прогресс должен быть заметен: не меньше 1,5 с
    const duration = Math.max(1500, (total / (200 * 1024 * 1024)) * 1000) / speed()
    const started = Date.now()

    return new Promise((resolve, reject) => {
      const abort = () => {
        clearInterval(timer)
        reject(new DOMException('Загрузка отменена', 'AbortError'))
      }
      if (signal?.aborted) return abort()
      signal?.addEventListener('abort', abort, { once: true })

      const timer = setInterval(() => {
        const k = Math.min(1, (Date.now() - started) / duration)
        onProgress?.({ loaded: Math.round(total * k), total })
        if (k < 1) return
        clearInterval(timer)
        signal?.removeEventListener('abort', abort)
        Object.assign(s, {
          uploadedAt: Date.now(),
          updatedAt: Date.now(),
          fail: !!files.audio?.name.toLowerCase().includes('fail'),
          draft: null,
          refine: null,
          message: null,
          files: {
            audio: files.audio?.name ?? null,
            transcript: files.transcript?.name ?? null,
            agenda: files.agenda?.name ?? null,
            attendees: files.attendees?.name ?? null,
            template: files.template?.name ?? null,
            archive: (files.archive ?? []).map((f) => f.name),
          },
        })
        save()
        resolve(status(s))
      }, 100)
    })
  },

  async restartProcessing(id) {
    await wait()
    const s = find(id)
    ensureIdle(s)
    if (s.uploadedAt === null)
      throw new ApiError(
        400,
        'Нет загруженной аудиозаписи или стенограммы — выполните загрузку файлов.',
      )
    Object.assign(s, { uploadedAt: Date.now(), updatedAt: Date.now(), fail: false, draft: null })
    save()
    return status(s)
  },

  async getStatus(id) {
    await wait(60, 160)
    return status(find(id))
  },

  async getDraft(id) {
    await wait()
    const s = find(id)
    return structuredClone(s.draft ?? emptyDraft(s))
  },

  async getTranscript(id) {
    await wait()
    const s = find(id)
    if (!s.draft) throw new ApiError(404, 'Стенограмма ещё не сформирована')
    return demoTranscript(sourceName(s))
  },

  async refine(id, req) {
    await wait()
    const s = find(id)
    ensureIdle(s)
    if (!s.draft) throw new ApiError(409, 'Проект протокола ещё не сформирован.')
    let draft: ProtocolDraft = structuredClone(s.draft)
    if (req.updated_metadata) draft.metadata = req.updated_metadata
    if (req.updated_agenda_items) draft.agenda_items = req.updated_agenda_items
    const cycle = draft.revision_cycle

    if (req.action === 'ai_regenerate') {
      if (cycle.current_cycle >= cycle.max_cycles) {
        cycle.is_escalated_to_manual = true
        s.draft = normalize(draft, s.files.archive)
        save()
        throw new ApiError(
          400,
          `Превышен лимит автоматических кругов правок (максимум ${cycle.max_cycles}). Переключено в режим ручной доработки.`,
        )
      }
      const feedback = req.user_feedback?.trim()
      if (!feedback) throw new ApiError(400, 'Опишите замечания для ИИ-агента.')
      cycle.current_cycle++
      cycle.is_escalated_to_manual = cycle.current_cycle >= cycle.max_cycles
      draft = normalize(draft, s.files.archive)
      Object.assign(s, {
        draft,
        refine: { startedAt: Date.now(), feedback },
        updatedAt: Date.now(),
      })
      save()
      return {
        session_id: id,
        status: 'refining',
        updated_draft: structuredClone(draft),
        revision_cycle: cycle,
        message: 'ИИ-правка запущена.',
      }
    }

    draft = normalize(draft, s.files.archive)
    Object.assign(s, { draft, message: null, updatedAt: Date.now() })
    save()
    return {
      session_id: id,
      status: 'ready',
      updated_draft: structuredClone(draft),
      revision_cycle: cycle,
      message: 'Правки сохранены.',
    }
  },

  async exportDocx(id) {
    await wait(400, 900)
    const s = find(id)
    ensureIdle(s)
    if (!s.draft) throw new ApiError(409, 'Проект протокола ещё не сформирован.')
    const file = new Blob([renderText(s.draft)], { type: 'text/plain;charset=utf-8' })
    return {
      session_id: id,
      file_name: `Протокол_совещания_${s.draft.metadata.meeting_date}.txt`,
      download_url: URL.createObjectURL(file),
      warnings: [],
      generated_at: iso(),
    }
  },
}
