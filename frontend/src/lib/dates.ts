/** <input type=date> отдаёт ГГГГ-ММ-ДД, API ждёт ДД.ММ.ГГГГ */
export function isoToRu(iso: string): string {
  const [y, m, d] = iso.split('-')
  return y && m && d ? `${d}.${m}.${y}` : iso
}

export function todayIso(now = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

const MONTHS = [
  'января',
  'февраля',
  'марта',
  'апреля',
  'мая',
  'июня',
  'июля',
  'августа',
  'сентября',
  'октября',
  'ноября',
  'декабря',
]

/** «20.10.2026» → «20 октября 2026 г.»; непонятный формат возвращается как есть */
export function ruLongDate(ru: string): string {
  const m = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(ru)
  const month = m ? MONTHS[Number(m[2]) - 1] : undefined
  return m && month ? `${Number(m[1])} ${month} ${m[3]} г.` : ru
}

/** ДД.ММ.ГГГГ → ГГГГ-ММ-ДД для <input type=date>; пусто или не дата — '' */
export function ruToIso(ru: string | null | undefined): string {
  const m = ru ? /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(ru) : null
  return m ? `${m[3]}-${m[2]}-${m[1]}` : ''
}
