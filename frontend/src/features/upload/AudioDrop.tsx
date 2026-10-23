import { useRef } from 'react'
import { FileAudioIcon, FileTextIcon, UploadSimpleIcon, XIcon } from '@phosphor-icons/react'
import { cx } from '@/lib/cx'
import { extOf, formatDuration, LONG_AUDIO_SEC, SLOTS } from '@/lib/files'
import { useFileDrop } from '@/lib/useFileDrop'
import { Button, IconButton } from '@/ui/Button'
import { FilePicker } from '@/ui/FilePicker'
import type { Picked } from './useUploadForm'

interface Props {
  audio: Picked | null
  transcript: Picked | null
  duration: number | null | undefined
  onAudio: (files: File[]) => void
  onTranscript: (files: File[]) => void
  onRemove: () => void
  disabled?: boolean
}

const ACCEPT = [...SLOTS.audio.accept, ...SLOTS.transcript.accept]

/**
 * Запись совещания — или, если записи нет, готовая стенограмма.
 * Что именно выбрано, понимаем по расширению файла.
 */
export function AudioDrop({
  audio,
  transcript,
  duration,
  onAudio,
  onTranscript,
  onRemove,
  disabled,
}: Props) {
  const input = useRef<HTMLInputElement>(null)
  const route = (files: File[]) => {
    const first = files[0]
    if (first && SLOTS.transcript.accept.includes(extOf(first.name))) onTranscript(files)
    else onAudio(files)
  }
  const { over, props } = useFileDrop(route, disabled)
  const open = () => input.current?.click()
  const picker = <FilePicker ref={input} accept={ACCEPT} onFiles={route} disabled={disabled} />
  const picked = audio ?? transcript

  if (!picked) {
    return (
      <div
        {...props}
        className={cx(
          'flex flex-col items-center gap-3 rounded-[var(--radius-card)] border-2 border-dashed px-6 py-9 text-center transition-colors',
          over ? 'border-primary bg-primary-soft' : 'border-line-strong bg-subtle',
        )}
      >
        {picker}
        <UploadSimpleIcon size={28} className={over ? 'text-primary' : 'text-ink-3'} />
        <p>
          Перетащите запись сюда или{' '}
          <Button variant="link" onClick={open} disabled={disabled}>
            выберите на компьютере
          </Button>
        </p>
        <p className="max-w-[520px] text-sm text-ink-3">
          {SLOTS.audio.formats}. Если записи нет, загрузите готовую стенограмму:{' '}
          {SLOTS.transcript.formats}.
        </p>
      </div>
    )
  }

  const Icon = audio ? FileAudioIcon : FileTextIcon
  return (
    <div
      {...props}
      className={cx(
        'rounded-[var(--radius-card)] border px-4 py-3 transition-colors',
        over ? 'border-primary bg-primary-soft' : 'border-line',
        picked.error && 'border-danger',
      )}
    >
      {picker}
      <div className="flex items-center gap-3">
        <Icon size={24} className={picked.error ? 'text-danger' : 'text-primary'} />
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium" title={picked.file.name}>
            {picked.file.name}
          </div>
          {!picked.error && audio && duration != null && (
            <div className="text-sm text-ink-3">{formatDuration(duration)}</div>
          )}
          {!picked.error && transcript && (
            <div className="text-sm text-ink-3">Готовая стенограмма</div>
          )}
        </div>
        <Button variant="link" onClick={open} disabled={disabled}>
          Заменить
        </Button>
        <IconButton
          label={audio ? 'Убрать аудиозапись' : 'Убрать стенограмму'}
          onClick={onRemove}
          disabled={disabled}
        >
          <XIcon size={18} />
        </IconButton>
      </div>
      {picked.error && <p className="mt-2 text-sm text-danger">{picked.error}</p>}
      {audio && duration != null && duration > LONG_AUDIO_SEC && (
        <p className="mt-2 text-sm text-warning">
          Запись длиннее двух часов — проверьте, что выбран нужный файл.
        </p>
      )}
    </div>
  )
}
