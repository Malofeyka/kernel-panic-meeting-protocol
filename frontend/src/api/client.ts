import type {
  ExportResponse,
  HealthResponse,
  MeetingTranscription,
  ProtocolDraft,
  RefineRequest,
  RefineResponse,
  SessionCreateRequest,
  SessionCreateResponse,
  SessionDetails,
  SessionFiles,
  SessionStatusResponse,
  SessionSummary,
  UploadProgress,
} from './types'
import { ApiError, detailMessage } from './errors'
import { uploadForm } from './upload'

export interface UploadOptions {
  onProgress?: (p: UploadProgress) => void
  signal?: AbortSignal
}

/** Единый интерфейс: реальный бэкенд и mock-слой взаимозаменяемы */
export interface ApiClient {
  health(): Promise<HealthResponse>
  listSessions(): Promise<SessionSummary[]>
  createSession(req: SessionCreateRequest): Promise<SessionCreateResponse>
  getSession(sessionId: string): Promise<SessionDetails>
  uploadFiles(
    sessionId: string,
    files: SessionFiles,
    opts?: UploadOptions,
  ): Promise<SessionStatusResponse>
  /** Повторный запуск обработки по уже загруженным файлам (после ошибки) */
  restartProcessing(sessionId: string): Promise<SessionStatusResponse>
  getStatus(sessionId: string): Promise<SessionStatusResponse>
  getDraft(sessionId: string): Promise<ProtocolDraft>
  getTranscript(sessionId: string): Promise<MeetingTranscription>
  /** Ручное сохранение или ИИ-правка (не больше max_cycles кругов) */
  refine(sessionId: string, req: RefineRequest): Promise<RefineResponse>
  exportDocx(sessionId: string): Promise<ExportResponse>
}

async function request<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'Сервер не отвечает')
  }
  const data: unknown = res.status === 204 ? null : await res.json().catch(() => null)
  if (!res.ok)
    throw new ApiError(res.status, detailMessage(data) ?? `Ошибка сервера (${res.status})`)
  return data as T
}

const sessionPath = (id: string) => `/api/sessions/${encodeURIComponent(id)}`

export const httpApi: ApiClient = {
  health: () => request('GET', '/api/health'),
  listSessions: () => request('GET', '/api/sessions'),
  createSession: (req) => request('POST', '/api/sessions/create', req),
  getSession: (id) => request('GET', sessionPath(id)),
  uploadFiles: (id, files, opts) => uploadForm(`${sessionPath(id)}/upload`, files, opts),
  restartProcessing: (id) => request('POST', `${sessionPath(id)}/process`),
  getStatus: (id) => request('GET', `${sessionPath(id)}/status`),
  getDraft: (id) => request('GET', `${sessionPath(id)}/draft`),
  getTranscript: (id) => request('GET', `${sessionPath(id)}/transcript`),
  refine: (id, req) => request('POST', `${sessionPath(id)}/refine`, req),
  exportDocx: (id) => request('POST', `${sessionPath(id)}/export`),
}
