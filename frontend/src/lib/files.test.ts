import { describe, expect, it } from 'vitest'
import {
  classifyFile,
  formatBytes,
  formatDuration,
  formatList,
  SLOTS,
  slotsFor,
  unsupportedText,
  validateFile,
} from './files'

const file = (name: string, size = 1024) => new File([new Uint8Array(size)], name)
const sized = (name: string, size: number) => {
  const f = file(name, 1)
  Object.defineProperty(f, 'size', { value: size })
  return f
}

describe('validateFile', () => {
  it('принимает допустимые форматы без учёта регистра', () => {
    expect(validateFile(file('Совещание.MP3'), SLOTS.audio)).toBeNull()
    expect(validateFile(file('запись.m4a'), SLOTS.audio)).toBeNull()
    expect(validateFile(file('повестка.PDF'), SLOTS.agenda)).toBeNull()
    expect(validateFile(file('совещание.mp4'), SLOTS.audio)).toBeNull()
    expect(validateFile(file('стенограмма.json'), SLOTS.transcript)).toBeNull()
  })

  it('объясняет, какой формат нужен', () => {
    expect(validateFile(file('запись.aiff'), SLOTS.audio)).toBe(
      'Формат .aiff не подходит. Нужен MP3, WAV, M4A, OGG, FLAC или видеозапись.',
    )
    expect(validateFile(file('бланк.pdf'), SLOTS.template)).toBe(
      'Формат .pdf не подходит. Нужен DOCX.',
    )
    expect(validateFile(file('README'), SLOTS.agenda)).toMatch(/^У файла нет расширения/)
  })

  it('отклоняет пустые и слишком большие файлы', () => {
    expect(validateFile(sized('a.wav', 0), SLOTS.audio)).toMatch(/пустой/)
    expect(validateFile(sized('a.wav', 3 * 1024 ** 3), SLOTS.audio)).toMatch(/больше 2,0 ГБ/)
    expect(validateFile(sized('a.docx', 51 * 1024 ** 2), SLOTS.agenda)).toMatch(/больше 50 МБ/)
  })
})

describe('classifyFile', () => {
  it.each([
    ['запись_20.10.wav', 'audio'],
    ['Повестка аппаратного.docx', 'agenda'],
    ['Список участников.pdf', 'attendees'],
    ['Состав.txt', 'attendees'],
    ['Шаблон протокола.docx', 'template'],
    ['Протокол №12 от 13.10.docx', 'archive'],
    ['Стенограмма совещания.docx', 'transcript'],
    ['meeting.json', 'transcript'],
    ['видео.mp4', 'audio'],
  ])('%s → %s', (name, slot) => {
    expect(classifyFile(file(name))).toBe(slot)
  })

  it('не угадывает без ключевых слов и при неподходящем формате', () => {
    expect(classifyFile(file('документ.docx'))).toBeNull()
    expect(classifyFile(file('шаблон.pdf'))).toBeNull()
    expect(classifyFile(file('протокол.xlsx'))).toBeNull()
  })
})

describe('slotsFor', () => {
  it('предлагает только поля, подходящие по формату', () => {
    expect(slotsFor(new File(['x'], 'справка.docx'))).toEqual([
      'transcript',
      'agenda',
      'attendees',
      'template',
      'archive',
    ])
    expect(slotsFor(new File(['x'], 'справка.pdf'))).toEqual([
      'transcript',
      'agenda',
      'attendees',
      'archive',
    ])
    expect(slotsFor(new File(['x'], 'запись.aiff'))).toEqual([])
    expect(unsupportedText(new File(['x'], 'запись.aiff'))).toBe(
      'Формат .aiff не поддерживается. Запись — MP3, WAV, M4A, OGG, FLAC или видеозапись, документы — DOCX, PDF или TXT.',
    )
  })
})

describe('форматирование', () => {
  it('formatBytes', () => {
    expect(formatBytes(512)).toBe('512 Б')
    expect(formatBytes(1536)).toBe('1,5 КБ')
    expect(formatBytes(312 * 1024 ** 2)).toBe('312 МБ')
  })

  it('formatDuration', () => {
    expect(formatDuration(5025)).toBe('1 ч 23 мин')
    expect(formatDuration(3600)).toBe('1 ч')
    expect(formatDuration(95)).toBe('1 мин 35 с')
    expect(formatDuration(42)).toBe('42 с')
  })

  it('formatList', () => {
    expect(formatList(['.docx'])).toBe('DOCX')
    expect(formatList(['.docx', '.pdf'])).toBe('DOCX или PDF')
  })
})
