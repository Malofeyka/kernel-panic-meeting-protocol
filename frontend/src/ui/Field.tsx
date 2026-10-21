import { useId, type InputHTMLAttributes } from 'react'
import { cx } from '@/lib/cx'

export const controlClass =
  'h-11 w-full rounded-[var(--radius-control)] border border-line-strong bg-surface px-3.5 text-[15px] text-ink ' +
  'transition-colors hover:border-ink-3 focus:border-primary focus:outline-none focus-visible:outline-none ' +
  'focus:ring-3 focus:ring-primary/15 disabled:bg-subtle disabled:text-ink-3'

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  label: string
}

export function Field({ label, className, ...rest }: Props) {
  const id = useId()
  return (
    <div className={cx('flex min-w-0 flex-col gap-1.5', className)}>
      <label htmlFor={id} className="text-sm text-ink-2">
        {label}
      </label>
      <input id={id} className={controlClass} {...rest} />
    </div>
  )
}
