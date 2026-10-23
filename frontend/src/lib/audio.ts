/**
 * Длительность аудио по метаданным, без декодирования всего файла.
 * null — браузер не смог прочитать (например, редкий кодек в .m4a): не ошибка, просто не показываем.
 */
export function readAudioDuration(file: File, timeoutMs = 5000): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file)
    const audio = new Audio()
    let done = false
    const finish = (value: number | null) => {
      if (done) return
      done = true
      clearTimeout(timer)
      audio.removeAttribute('src')
      audio.load()
      URL.revokeObjectURL(url)
      resolve(value)
    }
    const timer = setTimeout(() => finish(null), timeoutMs)
    audio.preload = 'metadata'
    audio.onloadedmetadata = () => finish(Number.isFinite(audio.duration) ? audio.duration : null)
    audio.onerror = () => finish(null)
    audio.src = url
  })
}
