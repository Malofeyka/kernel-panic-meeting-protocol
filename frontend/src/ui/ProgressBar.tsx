import { cx } from '@/lib/cx'

export function ProgressBar({
  value,
  label,
  tone = 'primary',
}: {
  value: number
  label: string
  tone?: 'primary' | 'danger'
}) {
  const v = Math.max(0, Math.min(100, value))
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(v)}
      className="h-1.5 w-full overflow-hidden rounded-full bg-line"
    >
      <div
        className={cx(
          'h-full rounded-full transition-[width] duration-700 ease-out',
          tone === 'primary' ? 'bg-primary' : 'bg-danger',
        )}
        style={{ width: `${v}%` }}
      />
    </div>
  )
}
