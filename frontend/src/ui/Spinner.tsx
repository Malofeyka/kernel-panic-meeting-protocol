import { cx } from '@/lib/cx'

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cx(
        'inline-block size-4 shrink-0 animate-[spin_0.8s_linear_infinite] rounded-full border-2 border-current border-r-transparent',
        className,
      )}
    />
  )
}
