import { describe, expect, it } from 'vitest'
import { isoToRu, ruLongDate, ruToIso, todayIso } from './dates'
import { plural } from './plural'

describe('даты', () => {
  it('isoToRu переводит ГГГГ-ММ-ДД в ДД.ММ.ГГГГ', () => {
    expect(isoToRu('2026-10-20')).toBe('20.10.2026')
  })
  it('ruToIso — для <input type=date>', () => {
    expect(ruToIso('20.11.2026')).toBe('2026-11-20')
    expect(ruToIso(null)).toBe('')
    expect(ruToIso('до пятницы')).toBe('')
  })
  it('todayIso с ведущими нулями', () => {
    expect(todayIso(new Date(2026, 0, 5))).toBe('2026-01-05')
  })
  it('ruLongDate', () => {
    expect(ruLongDate('20.10.2026')).toBe('20 октября 2026 г.')
    expect(ruLongDate('05.01.2027')).toBe('5 января 2027 г.')
    expect(ruLongDate('2026-10-20')).toBe('2026-10-20')
  })
})

describe('plural', () => {
  const forms: [string, string, string] = ['файл', 'файла', 'файлов']
  it.each([
    [1, 'файл'],
    [2, 'файла'],
    [5, 'файлов'],
    [11, 'файлов'],
    [12, 'файлов'],
    [21, 'файл'],
    [22, 'файла'],
    [111, 'файлов'],
  ])('%i → %s', (n, word) => expect(plural(n, forms)).toBe(word))
})
