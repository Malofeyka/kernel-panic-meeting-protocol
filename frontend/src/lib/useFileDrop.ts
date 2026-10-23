import { useRef, useState, type DragEvent } from 'react'

const hasFiles = (e: DragEvent) => e.dataTransfer.types.includes('Files')

/**
 * Drop-цель для файлов. Счётчик enter/leave — иначе подсветка мигает,
 * когда курсор проходит над дочерними элементами.
 * stopPropagation: файл, брошенный на строку, не попадает в пакетный drop страницы.
 */
export function useFileDrop(onFiles: (files: File[]) => void, disabled = false) {
  const depth = useRef(0)
  const [over, setOver] = useState(false)

  const props = {
    onDragEnter: (e: DragEvent) => {
      if (disabled || !hasFiles(e)) return
      e.preventDefault()
      e.stopPropagation()
      depth.current++
      setOver(true)
    },
    onDragOver: (e: DragEvent) => {
      if (disabled || !hasFiles(e)) return
      e.preventDefault()
      e.stopPropagation()
      e.dataTransfer.dropEffect = 'copy'
    },
    onDragLeave: (e: DragEvent) => {
      if (disabled || !hasFiles(e)) return
      e.stopPropagation()
      depth.current = Math.max(0, depth.current - 1)
      if (depth.current === 0) setOver(false)
    },
    onDrop: (e: DragEvent) => {
      if (disabled || !hasFiles(e)) return
      e.preventDefault()
      e.stopPropagation()
      depth.current = 0
      setOver(false)
      const files = Array.from(e.dataTransfer.files)
      if (files.length) onFiles(files)
    },
  }

  return { over, props }
}
