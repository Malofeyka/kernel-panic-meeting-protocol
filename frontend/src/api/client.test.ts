import { describe, expect, it } from 'vitest'
import { detailMessage } from './errors'
import { buildUploadForm } from './upload'

describe('detailMessage', () => {
  it('строка из HTTPException', () => {
    expect(detailMessage({ detail: 'Сессия не найдена' })).toBe('Сессия не найдена')
  })
  it('массив ошибок валидации 422', () => {
    expect(detailMessage({ detail: [{ msg: 'Field required' }, { msg: 'Invalid date' }] })).toBe(
      'Field required; Invalid date',
    )
  })
  it('нет detail', () => {
    expect(detailMessage(null)).toBeNull()
    expect(detailMessage({ message: 'x' })).toBeNull()
  })
})

describe('buildUploadForm', () => {
  const f = (name: string) => new File(['x'], name)

  it('поля называются как в upload_session_files', () => {
    const form = buildUploadForm({
      audio: f('a.wav'),
      agenda: f('agenda.docx'),
      attendees: f('people.pdf'),
      template: f('tpl.docx'),
      archive: [f('p1.docx'), f('p2.pdf')],
    })
    expect((form.get('audio_file') as File).name).toBe('a.wav')
    expect((form.get('agenda_file') as File).name).toBe('agenda.docx')
    expect((form.get('attendees_file') as File).name).toBe('people.pdf')
    expect((form.get('template_file') as File).name).toBe('tpl.docx')
    expect(form.getAll('archive_files').map((x) => (x as File).name)).toEqual(['p1.docx', 'p2.pdf'])
  })

  it('необязательные поля не отправляются', () => {
    const form = buildUploadForm({ audio: f('a.mp3'), agenda: null, archive: [] })
    expect([...form.keys()]).toEqual(['audio_file'])
  })

  it('стенограмма вместо записи', () => {
    const form = buildUploadForm({ transcript: f('стенограмма.txt') })
    expect([...form.keys()]).toEqual(['transcript_file'])
  })
})
