/**
 * Слоты загрузки (UI-01, openspec/specs/review-ui/spec.md) и правила валидации.
 * Форматы — по контракту POST /api/sessions/{id}/upload.
 */

export type SlotId = 'audio' | 'transcript' | 'agenda' | 'attendees' | 'template' | 'archive'
/** Материалы к совещанию (кроме самой записи или стенограммы) */
export type DocSlotId = Exclude<SlotId, 'audio' | 'transcript'>

export interface SlotSpec {
  id: SlotId
  label: string
  /** Расширения в нижнем регистре, с точкой */
  accept: string[]
  /** Как назвать допустимые форматы в подсказках и ошибках */
  formats: string
  maxBytes: number
  multiple: boolean
  required: boolean
}

const MB = 1024 * 1024
const GB = 1024 * MB

export const SLOTS: Record<SlotId, SlotSpec> = {
  audio: {
    id: 'audio',
    label: 'Аудиозапись совещания',
    // Как AUDIO_SUFFIXES в backend/app/api/routes.py: звук берётся и из видеозаписи
    accept: [
      '.mp3',
      '.wav',
      '.m4a',
      '.ogg',
      '.flac',
      '.aac',
      '.wma',
      '.mp4',
      '.mkv',
      '.webm',
      '.mov',
      '.avi',
    ],
    formats: 'MP3, WAV, M4A, OGG, FLAC или видеозапись',
    maxBytes: 2 * GB,
    multiple: false,
    required: true,
  },
  transcript: {
    id: 'transcript',
    label: 'Стенограмма',
    accept: ['.txt', '.docx', '.pdf', '.json'],
    formats: 'TXT, DOCX, PDF или JSON',
    maxBytes: 50 * MB,
    multiple: false,
    required: false,
  },
  agenda: {
    id: 'agenda',
    label: 'Повестка',
    accept: ['.docx', '.pdf', '.txt'],
    formats: 'DOCX, PDF или TXT',
    maxBytes: 50 * MB,
    multiple: false,
    required: false,
  },
  attendees: {
    id: 'attendees',
    label: 'Список участников',
    accept: ['.docx', '.pdf', '.txt'],
    formats: 'DOCX, PDF или TXT',
    maxBytes: 50 * MB,
    multiple: false,
    required: false,
  },
  template: {
    id: 'template',
    label: 'Шаблон протокола',
    accept: ['.docx'],
    formats: 'DOCX',
    maxBytes: 50 * MB,
    multiple: false,
    required: false,
  },
  archive: {
    id: 'archive',
    label: 'Предыдущие протоколы',
    accept: ['.docx', '.pdf', '.txt'],
    formats: 'DOCX, PDF или TXT',
    maxBytes: 50 * MB,
    multiple: true,
    required: false,
  },
}

export const DOC_SLOTS: DocSlotId[] = ['agenda', 'attendees', 'template', 'archive']

/** Длительность, после которой предупреждаем: по ТЗ записи 1–1,5 ч */
export const LONG_AUDIO_SEC = 2 * 60 * 60

export function extOf(name: string): string {
  const i = name.lastIndexOf('.')
  return i > 0 ? name.slice(i).toLowerCase() : ''
}

/** «.wav, .mp3» → «WAV, MP3 или M4A» */
export function formatList(accept: string[]): string {
  const names = accept.map((e) => e.slice(1).toUpperCase())
  if (names.length < 2) return names.join('')
  return `${names.slice(0, -1).join(', ')} или ${names.at(-1)}`
}

/** Ошибка отвечает на «что не так» и «что нужно»; null — файл подходит */
export function validateFile(file: File, slot: SlotSpec): string | null {
  const ext = extOf(file.name)
  if (!slot.accept.includes(ext)) {
    const what = ext ? `Формат ${ext} не подходит` : 'У файла нет расширения'
    return `${what}. Нужен ${slot.formats}.`
  }
  if (file.size === 0) return 'Файл пустой. Выберите другой.'
  if (file.size > slot.maxBytes) {
    return `Файл больше ${formatBytes(slot.maxBytes)}. Сожмите запись или выберите другой файл.`
  }
  return null
}

const AUDIO_EXT = new Set(SLOTS.audio.accept)

/** Ключевые слова в имени файла → слот. Порядок важен: «шаблон протокола» — шаблон, не архив */
const KEYWORDS: [RegExp, Exclude<SlotId, 'audio'>][] = [
  [/стенограмм|расшифровк|transcript/i, 'transcript'],
  [/шаблон|бланк|template/i, 'template'],
  [/повестк|agenda/i, 'agenda'],
  [/участник|список|состав|attendee|participant/i, 'attendees'],
  [/протокол|protocol/i, 'archive'],
]

const SLOT_ORDER: SlotId[] = ['audio', 'transcript', 'agenda', 'attendees', 'template', 'archive']

/** Поля, в которые файл можно положить по формату */
export function slotsFor(file: File): SlotId[] {
  const ext = extOf(file.name)
  return SLOT_ORDER.filter((slot) => SLOTS[slot].accept.includes(ext))
}

/** Сообщение для файла, который не подходит ни под одно поле */
export function unsupportedText(file: File): string {
  const ext = extOf(file.name)
  const what = ext ? `Формат ${ext} не поддерживается` : 'У файла нет расширения'
  return `${what}. Запись — ${SLOTS.audio.formats}, документы — DOCX, PDF или TXT.`
}

/**
 * Раскладка файла при пакетном перетаскивании. Аудио — по расширению,
 * документы — по имени. null — не распознан, спрашиваем пользователя.
 */
export function classifyFile(file: File): SlotId | null {
  const ext = extOf(file.name)
  if (AUDIO_EXT.has(ext)) return 'audio'
  if (ext === '.json') return 'transcript'
  for (const [re, slot] of KEYWORDS) {
    if (re.test(file.name) && SLOTS[slot].accept.includes(ext)) return slot
  }
  return null
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`
  const units = ['КБ', 'МБ', 'ГБ']
  let v = bytes / 1024
  let u = 0
  while (v >= 1024 && u < units.length - 1) {
    v /= 1024
    u++
  }
  const digits = v < 10 ? 1 : 0
  return `${v.toFixed(digits).replace('.', ',')} ${units[u]}`
}

/** 5025 → «1 ч 23 мин»; 95 → «1 мин 35 с» */
export function formatDuration(sec: number): string {
  const s = Math.round(sec)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h > 0) return m > 0 ? `${h} ч ${m} мин` : `${h} ч`
  if (m > 0) return `${m} мин ${s % 60} с`
  return `${s} с`
}

/** Стабильный ключ файла для списков и дедупликации */
export const fileKey = (f: File) => `${f.name}:${f.size}:${f.lastModified}`
