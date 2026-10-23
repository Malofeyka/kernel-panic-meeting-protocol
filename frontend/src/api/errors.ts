export class ApiError extends Error {
  /** HTTP-статус; 0 — сервер не ответил (сеть, бэкенд не запущен) */
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** FastAPI отдаёт detail строкой (HTTPException) или массивом (422 валидации) */
export function detailMessage(data: unknown): string | null {
  if (!data || typeof data !== 'object' || !('detail' in data)) return null
  const { detail } = data as { detail: unknown }
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d: unknown) =>
        d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : String(d),
      )
      .join('; ')
  }
  return null
}

export const isAbortError = (e: unknown) => e instanceof DOMException && e.name === 'AbortError'
