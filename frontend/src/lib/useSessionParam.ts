import { useCallback, useEffect, useState } from 'react'

const PARAM = 'session'

const read = () => new URLSearchParams(window.location.search).get(PARAM)

/**
 * id рабочей сессии в адресе (?session=…): ссылку можно открыть снова
 * после перезагрузки или закрытия вкладки — обработка продолжается на сервере.
 */
export function useSessionParam() {
  const [sessionId, setState] = useState<string | null>(read)

  useEffect(() => {
    const onPop = () => setState(read())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const setSessionId = useCallback((id: string | null) => {
    const url = new URL(window.location.href)
    if (id) url.searchParams.set(PARAM, id)
    else url.searchParams.delete(PARAM)
    // push: «Назад» в браузере возвращает к форме загрузки
    window.history.pushState(null, '', url)
    setState(id)
  }, [])

  return [sessionId, setSessionId] as const
}
