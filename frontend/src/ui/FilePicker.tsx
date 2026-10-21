import { forwardRef, type ChangeEvent } from 'react'

interface Props {
  accept: string[]
  multiple?: boolean
  onFiles: (files: File[]) => void
  disabled?: boolean
}

/** Скрытый <input type=file>; открывается через ref.click() из кнопки или зоны */
export const FilePicker = forwardRef<HTMLInputElement, Props>(function FilePicker(
  { accept, multiple, onFiles, disabled },
  ref,
) {
  const onChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    // Сброс: повторный выбор того же файла тоже вызовет onChange
    e.target.value = ''
    if (files.length) onFiles(files)
  }
  return (
    <input
      ref={ref}
      type="file"
      className="sr-only"
      tabIndex={-1}
      aria-hidden
      accept={accept.join(',')}
      multiple={multiple}
      disabled={disabled}
      onChange={onChange}
    />
  )
})
