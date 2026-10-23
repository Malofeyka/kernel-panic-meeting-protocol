import { describe, expect, it } from 'vitest'
import { fileKey } from '@/lib/files'
import { initial, reducer } from './useUploadForm'

const f = (name: string) => new File(['x'], name, { lastModified: 1 })

describe('пакетная раскладка файлов', () => {
  it('раскладывает по слотам, нераспознанные — отдельно', () => {
    const s = reducer(initial(), {
      type: 'batch',
      files: [
        f('запись.wav'),
        f('Повестка.docx'),
        f('Список участников.pdf'),
        f('Протокол 1.docx'),
        f('Протокол 2.pdf'),
        f('справка.docx'),
      ],
    })
    expect(s.audio?.file.name).toBe('запись.wav')
    expect(s.agenda?.file.name).toBe('Повестка.docx')
    expect(s.attendees?.file.name).toBe('Список участников.pdf')
    expect(s.archive.map((p) => p.file.name)).toEqual(['Протокол 1.docx', 'Протокол 2.pdf'])
    expect(s.unsorted.map((x) => x.name)).toEqual(['справка.docx'])
  })

  it('вторая аудиозапись в пачке не заменяет первую молча', () => {
    const s = reducer(initial(), { type: 'batch', files: [f('a.wav'), f('b.mp3')] })
    expect(s.audio?.file.name).toBe('a.wav')
    expect(s.unsorted.map((x) => x.name)).toEqual(['b.mp3'])
  })

  it('неподдерживаемый формат в пачке блокирует отправку', () => {
    const s = reducer(initial(), { type: 'batch', files: [f('запись.wav'), f('запись.aiff')] })
    expect(s.unsorted.map((x) => x.name)).toEqual(['запись.aiff'])
  })

  it('стенограмма вместо записи: одно заменяет другое', () => {
    let s = reducer(initial(), { type: 'batch', files: [f('Стенограмма.txt'), f('Повестка.docx')] })
    expect(s.transcript?.file.name).toBe('Стенограмма.txt')
    expect(s.agenda?.file.name).toBe('Повестка.docx')
    s = reducer(s, { type: 'put', slot: 'audio', files: [f('запись.mp3')] })
    expect(s.audio?.file.name).toBe('запись.mp3')
    expect(s.transcript).toBeNull()
  })

  it('назначение нераспознанного файла с валидацией', () => {
    let s = reducer(initial(), { type: 'batch', files: [f('справка.pdf')] })
    s = reducer(s, { type: 'assign', key: fileKey(f('справка.pdf')), slot: 'template' })
    expect(s.unsorted).toHaveLength(0)
    expect(s.template?.error).toMatch(/Нужен DOCX/)
  })

  it('архив без дублей', () => {
    let s = reducer(initial(), { type: 'put', slot: 'archive', files: [f('p.docx')] })
    s = reducer(s, { type: 'put', slot: 'archive', files: [f('p.docx'), f('q.pdf')] })
    expect(s.archive.map((p) => p.file.name)).toEqual(['p.docx', 'q.pdf'])
  })
})
