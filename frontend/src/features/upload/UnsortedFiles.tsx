import { useEffect, useRef } from 'react'
import { CaretDownIcon, XIcon } from '@phosphor-icons/react'
import { fileKey, SLOTS, slotsFor, unsupportedText, type SlotId } from '@/lib/files'
import { IconButton } from '@/ui/Button'
import { controlClass } from '@/ui/Field'

interface Props {
  files: File[]
  onAssign: (key: string, slot: SlotId) => void
  onDismiss: (key: string) => void
  disabled?: boolean
}

/** Файлы из пакетного перетаскивания, которые не удалось разложить по имени */
export function UnsortedFiles({ files, onAssign, onDismiss, disabled }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const prev = useRef(0)
  useEffect(() => {
    if (files.length > prev.current)
      ref.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    prev.current = files.length
  }, [files.length])

  if (files.length === 0) return null
  const askable = files.some((f) => slotsFor(f).length > 0)
  return (
    <div ref={ref} className="mt-6 rounded-[var(--radius-card)] bg-warning-soft px-5 py-4">
      <p className="font-medium">
        {askable ? 'Укажите, что это за файлы' : 'Эти файлы нельзя загрузить'}
      </p>
      <ul className="mt-3 flex flex-col gap-2">
        {files.map((f) => {
          const key = fileKey(f)
          const options = slotsFor(f)
          return (
            <li key={key} className="flex items-center gap-3">
              <span className="min-w-0 flex-1" title={f.name}>
                <span className="block truncate">{f.name}</span>
                {options.length === 0 && (
                  <span className="block text-danger">{unsupportedText(f)}</span>
                )}
              </span>
              {options.length > 0 && (
                <div className="relative w-60 shrink-0">
                  <select
                    aria-label={`Что за файл ${f.name}`}
                    className={`${controlClass} h-10 cursor-pointer appearance-none pr-9`}
                    value=""
                    disabled={disabled}
                    onChange={(e) => onAssign(key, e.target.value as SlotId)}
                  >
                    <option value="" disabled>
                      Выберите
                    </option>
                    {options.map((slot) => (
                      <option key={slot} value={slot}>
                        {SLOTS[slot].label}
                      </option>
                    ))}
                  </select>
                  <CaretDownIcon
                    size={16}
                    className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-ink-3"
                  />
                </div>
              )}
              <IconButton
                label={`Убрать ${f.name}`}
                onClick={() => onDismiss(key)}
                disabled={disabled}
              >
                <XIcon size={16} />
              </IconButton>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
