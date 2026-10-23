import { CheckCircleIcon, WarningCircleIcon, WarningIcon } from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import { cx } from '@/lib/cx'

const TONES = {
  danger: { Icon: WarningCircleIcon, bg: 'bg-danger-soft', fg: 'text-danger' },
  warning: { Icon: WarningIcon, bg: 'bg-warning-soft', fg: 'text-warning' },
  success: { Icon: CheckCircleIcon, bg: 'bg-success-soft', fg: 'text-success' },
}

/** Сообщение об ошибке или предупреждение: что случилось и что делать */
export function Notice({
  tone = 'danger',
  title,
  children,
  action,
  className,
}: {
  tone?: 'danger' | 'warning' | 'success'
  title: ReactNode
  children?: ReactNode
  action?: ReactNode
  className?: string
}) {
  const { Icon, bg, fg } = TONES[tone]
  return (
    <div
      role={tone === 'danger' ? 'alert' : 'status'}
      className={cx('flex gap-3 rounded-[var(--radius-card)] px-5 py-4', bg, className)}
    >
      <Icon
        size={20}
        weight={tone === 'success' ? 'fill' : 'regular'}
        className={cx('mt-0.5 shrink-0', fg)}
      />
      <div className="min-w-0 flex-1">
        <div className="font-medium">{title}</div>
        {children && <div className="mt-0.5 text-ink-2">{children}</div>}
        {action && <div className="mt-3">{action}</div>}
      </div>
    </div>
  )
}
