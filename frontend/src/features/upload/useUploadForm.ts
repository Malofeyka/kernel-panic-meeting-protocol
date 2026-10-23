import { useEffect, useMemo, useReducer } from 'react'
import type { SessionFiles } from '@/api'
import { readAudioDuration } from '@/lib/audio'
import { todayIso } from '@/lib/dates'
import {
  classifyFile,
  fileKey,
  SLOTS,
  slotsFor,
  validateFile,
  type DocSlotId,
  type SlotId,
} from '@/lib/files'

export interface Picked {
  file: File
  /** Текст ошибки валидации; файл с ошибкой виден в строке, но не отправляется */
  error: string | null
}

export interface FormState {
  title: string
  /** ГГГГ-ММ-ДД, как отдаёт <input type=date> */
  date: string
  /** Запись совещания; взаимоисключается со стенограммой */
  audio: Picked | null
  /** Готовая стенограмма вместо записи */
  transcript: Picked | null
  /** undefined — ещё читаем, null — браузер не смог определить */
  audioDuration: number | null | undefined
  agenda: Picked | null
  attendees: Picked | null
  template: Picked | null
  archive: Picked[]
  /** Файлы из пакетного перетаскивания, которые не удалось разложить по имени */
  unsorted: File[]
}

type Action =
  | { type: 'field'; name: 'title' | 'date'; value: string }
  | { type: 'put'; slot: SlotId; files: File[] }
  | { type: 'remove'; slot: SlotId; key?: string }
  | { type: 'batch'; files: File[] }
  | { type: 'assign'; key: string; slot: SlotId }
  | { type: 'dismiss'; key: string }
  | { type: 'duration'; key: string; value: number | null }

const pick = (file: File, slot: SlotId): Picked => ({
  file,
  error: validateFile(file, SLOTS[slot]),
})

function put(state: FormState, slot: SlotId, files: File[]): FormState {
  const first = files[0]
  if (!first) return state
  if (slot === 'archive') {
    const known = new Set(state.archive.map((p) => fileKey(p.file)))
    const added = files.filter((f) => !known.has(fileKey(f))).map((f) => pick(f, 'archive'))
    return { ...state, archive: [...state.archive, ...added] }
  }
  if (slot === 'audio') {
    return { ...state, audio: pick(first, 'audio'), transcript: null, audioDuration: undefined }
  }
  if (slot === 'transcript') {
    return {
      ...state,
      transcript: pick(first, 'transcript'),
      audio: null,
      audioDuration: undefined,
    }
  }
  return { ...state, [slot]: pick(first, slot) }
}

export function reducer(state: FormState, action: Action): FormState {
  switch (action.type) {
    case 'field':
      return { ...state, [action.name]: action.value }
    case 'put':
      return put(state, action.slot, action.files)
    case 'remove':
      if (action.slot === 'archive') {
        return { ...state, archive: state.archive.filter((p) => fileKey(p.file) !== action.key) }
      }
      if (action.slot === 'audio' || action.slot === 'transcript')
        return { ...state, audio: null, transcript: null, audioDuration: undefined }
      return { ...state, [action.slot]: null }
    case 'batch': {
      let next = state
      const unsorted: File[] = []
      let sourceTaken = false
      for (const file of action.files) {
        const slot = classifyFile(file)
        const isSource = slot === 'audio' || slot === 'transcript'
        // Вторая запись или стенограмма в одной пачке — спрашиваем, а не заменяем молча
        if (slot === null || (isSource && sourceTaken)) unsorted.push(file)
        else {
          if (isSource) sourceTaken = true
          next = put(next, slot, [file])
        }
      }
      const known = new Set(next.unsorted.map(fileKey))
      return {
        ...next,
        unsorted: [...next.unsorted, ...unsorted.filter((f) => !known.has(fileKey(f)))],
      }
    }
    case 'assign': {
      const file = state.unsorted.find((f) => fileKey(f) === action.key)
      if (!file) return state
      const rest = { ...state, unsorted: state.unsorted.filter((f) => f !== file) }
      return put(rest, action.slot, [file])
    }
    case 'dismiss':
      return { ...state, unsorted: state.unsorted.filter((f) => fileKey(f) !== action.key) }
    case 'duration':
      // Ответ мог прийти для уже заменённого файла
      if (!state.audio || fileKey(state.audio.file) !== action.key) return state
      return { ...state, audioDuration: action.value }
  }
}

export const initial = (): FormState => ({
  title: 'Аппаратное совещание',
  date: todayIso(),
  audio: null,
  transcript: null,
  audioDuration: undefined,
  agenda: null,
  attendees: null,
  template: null,
  archive: [],
  unsorted: [],
})

export function pickedFor(state: FormState, slot: DocSlotId): Picked[] {
  if (slot === 'archive') return state.archive
  const p = state[slot]
  return p ? [p] : []
}

export function useUploadForm() {
  const [state, dispatch] = useReducer(reducer, undefined, initial)

  const audioFile = state.audio && !state.audio.error ? state.audio.file : null
  useEffect(() => {
    if (!audioFile) return
    let alive = true
    void readAudioDuration(audioFile).then((value) => {
      if (alive) dispatch({ type: 'duration', key: fileKey(audioFile), value })
    })
    return () => {
      alive = false
    }
  }, [audioFile])

  const summary = useMemo(() => {
    const picked = [
      state.audio,
      state.transcript,
      state.agenda,
      state.attendees,
      state.template,
      ...state.archive,
    ].filter((p): p is Picked => p !== null)
    const invalid = picked.filter((p) => p.error).length
    const bytes = picked.reduce((sum, p) => sum + p.file.size, 0)

    // Первая причина, по которой нельзя начать, — показываем рядом с кнопкой
    let blocker: string | null = null
    if (!state.audio && !state.transcript) blocker = 'Добавьте аудиозапись совещания'
    else if (invalid > 0) blocker = 'Уберите или замените файлы с ошибками'
    else if (state.unsorted.some((f) => slotsFor(f).length === 0))
      blocker = 'Уберите файлы неподдерживаемого формата'
    else if (state.unsorted.length > 0) blocker = 'Укажите, куда отнести нераспознанные файлы'
    else if (!state.title.trim()) blocker = 'Укажите наименование совещания'
    else if (!state.date) blocker = 'Укажите дату совещания'

    return { count: picked.length, bytes, blocker }
  }, [state])

  const files = (): SessionFiles | null => {
    if (summary.blocker) return null
    return {
      audio: state.audio?.file ?? null,
      transcript: state.transcript?.file ?? null,
      agenda: state.agenda?.file ?? null,
      attendees: state.attendees?.file ?? null,
      template: state.template?.file ?? null,
      archive: state.archive.map((p) => p.file),
    }
  }

  return { state, dispatch, summary, files }
}
