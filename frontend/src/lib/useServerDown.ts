import { useEffect, useState } from 'react'
import { api } from '@/api'

/** true, если сервер не отвечает. Проверяем раз в 30 с; пока всё в порядке — ничего не показываем */
export function useServerDown(): boolean {
  const [down, setDown] = useState(false)
  useEffect(() => {
    let alive = true
    const check = () =>
      api
        .health()
        .then(() => alive && setDown(false))
        .catch(() => alive && setDown(true))
    void check()
    const t = setInterval(check, 30_000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])
  return down
}
