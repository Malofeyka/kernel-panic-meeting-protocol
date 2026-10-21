import { useRef } from 'react'
import { XIcon } from '@phosphor-icons/react'
import { cx } from '@/lib/cx'
import { fileKey, SLOTS, type DocSlotId } from '@/lib/files'
import { useFileDrop } from '@/lib/useFileDrop'
import { Button, IconButton } from '@/ui/Button'
import { FilePicker } from '@/ui/FilePicker'
import type { Picked } from './useUploadForm'

interface Props {
  slot: DocSlotId
  picked: Picked[]
  onFiles: (files: File[]) => void
  onRemove: (key: string) => void
  disabled?: boolean
}

/** Строка документа: название слева, файл или кнопка выбора справа; принимает drop */
export function DocSlotRow({ slot, picked, onFiles, onRemove, disabled }: Props) {
  const spec = SLOTS[slot]
  const input = useRef<HTMLInputElement>(null)
  const { over, props } = useFileDrop(onFiles, disabled)
  const canAdd = spec.multiple || picked.length === 0

  return (
    <li
      {...props}
      className={cx(
        'grid gap-x-6 gap-y-1 py-3.5 transition-colors sm:grid-cols-[200px_minmax(0,1fr)]',
        over && 'bg-primary-soft',
      )}
    >
      <FilePicker
        ref={input}
        accept={spec.accept}
        multiple={spec.multiple}
        onFiles={onFiles}
        disabled={disabled}
      />
      <div className="pt-1.5 text-ink-2">{spec.label}</div>
      <div className="flex min-w-0 flex-col items-start gap-1">
        {picked.map(({ file, error }) => (
          <div key={fileKey(file)} className="flex w-full min-w-0 flex-col">
            <div className="flex min-w-0 items-center gap-1">
              <span
                className={cx('min-w-0 truncate pt-0.5', error && 'text-danger')}
                title={file.name}
              >
                {file.name}
              </span>
              <IconButton
                label={`Убрать ${file.name}`}
                onClick={() => onRemove(fileKey(file))}
                disabled={disabled}
              >
                <XIcon size={16} />
              </IconButton>
            </div>
            {error && <p className="text-sm text-danger">{error}</p>}
          </div>
        ))}
        {canAdd && (
          <Button
            size="sm"
            onClick={() => input.current?.click()}
            disabled={disabled}
            className={picked.length > 0 ? 'mt-1' : undefined}
          >
            {picked.length > 0 ? 'Добавить ещё' : 'Выбрать файл'}
          </Button>
        )}
      </div>
    </li>
  )
}
