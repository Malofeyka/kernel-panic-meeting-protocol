import type { ProcessingStep } from '@/api'

/** Этапы конвейера (design.md §2), которые видит секретарь после загрузки */
export function stepsFor(fromTranscript: boolean) {
  return [
    fromTranscript ? 'Разбор стенограммы' : 'Распознавание речи',
    'Извлечение решений и поручений',
    'Сверка с повесткой и материалами',
    'Формирование проекта протокола',
  ]
}

export const STEP_COUNT = 4

/** Индекс текущего этапа; STEP_COUNT — всё готово, -1 — неизвестно (ошибка) */
export function stepIndex(status: ProcessingStep): number {
  switch (status) {
    case 'idle':
    case 'uploading':
    case 'transcribing':
      return 0
    case 'extracting':
    case 'refining':
      return 1
    case 'cross_checking':
      return 2
    case 'ready':
      return STEP_COUNT
    case 'failed':
      return -1
  }
}

/** Пока сервер в этих статусах, опрашиваем /status */
export const BUSY: ReadonlySet<ProcessingStep> = new Set([
  'uploading',
  'transcribing',
  'extracting',
  'cross_checking',
  'refining',
])
