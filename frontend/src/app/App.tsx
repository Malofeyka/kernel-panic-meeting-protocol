import { useEffect } from 'react'
import { cx } from '@/lib/cx'
import { SessionView } from '@/features/session/SessionView'
import { UploadPage } from '@/features/upload/UploadPage'
import { useSessionParam } from '@/lib/useSessionParam'
import { Header } from './Header'

export function App() {
  const [sessionId, setSessionId] = useSessionParam()

  // Файл, брошенный мимо drop-зон, браузер открыл бы вместо приложения
  useEffect(() => {
    const block = (e: DragEvent) => {
      if (e.dataTransfer?.types.includes('Files')) e.preventDefault()
    }
    window.addEventListener('dragover', block)
    window.addEventListener('drop', block)
    return () => {
      window.removeEventListener('dragover', block)
      window.removeEventListener('drop', block)
    }
  }, [])

  return (
    <>
      <Header wide={!!sessionId} onHome={() => setSessionId(null)} />
      {/* Экран сессии шире: документ и колонка замечаний рядом */}
      <main
        className={cx('mx-auto px-6 pt-10 pb-20', sessionId ? 'max-w-[1280px]' : 'max-w-[880px]')}
      >
        {sessionId ? (
          <SessionView key={sessionId} sessionId={sessionId} onNew={() => setSessionId(null)} />
        ) : (
          <UploadPage onStarted={setSessionId} onOpen={setSessionId} />
        )}
      </main>
    </>
  )
}
