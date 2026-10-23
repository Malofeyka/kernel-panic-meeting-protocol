import { useEffect, useRef } from 'react'

interface Options {
  /** Интервал при активной вкладке, мс */
  interval?: number
  /** Интервал при скрытой вкладке: обработка идёт до 45 мин, не дёргаем сервер зря */
  hiddenInterval?: number
  enabled?: boolean
}

/**
 * Повторяет tick, пока он возвращает true. Следующий вызов — только после завершения
 * предыдущего (без наложения запросов). При возврате на вкладку опрашивает сразу.
 */
export function usePolling(
  tick: () => Promise<boolean>,
  { interval = 2000, hiddenInterval = 10000, enabled = true }: Options = {},
) {
  const tickRef = useRef(tick)
  useEffect(() => {
    tickRef.current = tick
  })

  useEffect(() => {
    if (!enabled) return
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let running = false

    const run = async () => {
      if (stopped || running) return
      running = true
      clearTimeout(timer)
      let again = true
      try {
        again = await tickRef.current()
      } catch {
        // Сбой одного опроса не останавливает поллинг: сеть могла моргнуть
      }
      running = false
      if (stopped || !again) return
      timer = setTimeout(run, document.hidden ? hiddenInterval : interval)
    }

    const onVisible = () => {
      if (!document.hidden) void run()
    }

    void run()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      stopped = true
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [enabled, interval, hiddenInterval])
}
