import type { SessionFiles, SessionStatusResponse } from './types'
import type { UploadOptions } from './client'
import { ApiError, detailMessage } from './errors'

/** Имена полей формы — как в upload_session_files (backend/app/api/routes.py) */
export function buildUploadForm(files: SessionFiles): FormData {
  const form = new FormData()
  if (files.audio) form.append('audio_file', files.audio)
  if (files.transcript) form.append('transcript_file', files.transcript)
  if (files.agenda) form.append('agenda_file', files.agenda)
  if (files.attendees) form.append('attendees_file', files.attendees)
  if (files.template) form.append('template_file', files.template)
  for (const f of files.archive ?? []) form.append('archive_files', f)
  return form
}

/** XHR, а не fetch: только у XHR есть событие прогресса отправки */
export function uploadForm(
  url: string,
  files: SessionFiles,
  { onProgress, signal }: UploadOptions = {},
): Promise<SessionStatusResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', url)
    xhr.responseType = 'json'

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress?.({ loaded: e.loaded, total: e.total })
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response as SessionStatusResponse)
      else
        reject(
          new ApiError(
            xhr.status,
            detailMessage(xhr.response) ?? `Ошибка загрузки (${xhr.status})`,
          ),
        )
    }
    xhr.onerror = () => reject(new ApiError(0, 'Сервер не отвечает'))
    xhr.onabort = () => reject(new DOMException('Загрузка отменена', 'AbortError'))

    if (signal) {
      if (signal.aborted) return reject(new DOMException('Загрузка отменена', 'AbortError'))
      signal.addEventListener('abort', () => xhr.abort(), { once: true })
    }
    xhr.send(buildUploadForm(files))
  })
}
