import { ApiError } from '@/api'

/** Текст ошибки для человека: что случилось и что делать */
export function errorText(error: unknown): { title: string; hint: string } {
  const status = error instanceof ApiError ? error.status : null
  const message = error instanceof Error ? error.message : String(error)
  switch (true) {
    case status === 0:
      return {
        title: 'Сервер не отвечает',
        hint: 'Проверьте, что серверная часть запущена на этом компьютере, и повторите.',
      }
    case status === 404:
      return {
        title: 'Сессия не найдена',
        hint: 'Возможно, сервер перезапускали. Загрузите материалы заново.',
      }
    case status === 409:
      return { title: message, hint: 'Дождитесь завершения обработки и повторите.' }
    case status === 413:
      return {
        title: 'Файлы слишком большие',
        hint: 'Сервер не принял такой объём. Сожмите запись.',
      }
    case status === 400 || status === 422:
      return { title: message, hint: 'Проверьте файлы и реквизиты совещания.' }
    case status !== null && status >= 500:
      return {
        title: 'Ошибка на сервере',
        hint: 'Повторите через минуту. Если ошибка повторяется — сообщите администратору.',
      }
    default:
      return { title: message, hint: 'Повторите попытку.' }
  }
}
