import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { cx } from '@/lib/cx'
import { Spinner } from './Spinner'

type Variant = 'primary' | 'secondary' | 'link'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: 'md' | 'sm'
  icon?: ReactNode
  loading?: boolean
}

const VARIANT: Record<Variant, string> = {
  primary:
    'bg-primary text-white hover:bg-primary-hover disabled:bg-line-strong disabled:text-white',
  secondary:
    'bg-surface text-primary border border-line-strong hover:border-primary hover:bg-primary-soft disabled:text-ink-3 disabled:border-line disabled:bg-surface',
  link: 'text-primary hover:text-primary-hover underline-offset-4 hover:underline disabled:text-ink-3',
}

export function Button({
  variant = 'secondary',
  size = 'md',
  icon,
  loading,
  className,
  children,
  disabled,
  type = 'button',
  ...rest
}: Props) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={cx(
        'inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 font-medium whitespace-nowrap transition-colors duration-150 disabled:cursor-not-allowed',
        variant !== 'link' && 'rounded-[var(--radius-control)]',
        variant !== 'link' && (size === 'md' ? 'h-11 px-5 text-[15px]' : 'h-9 px-3.5 text-sm'),
        variant === 'link' && 'text-[15px]',
        VARIANT[variant],
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner /> : icon}
      {children}
    </button>
  )
}

/** Кнопка-иконка без подписи (убрать файл и т. п.) — подпись обязательна для скринридеров */
export function IconButton({
  label,
  children,
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cx(
        'inline-flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-[var(--radius-control)] text-ink-3 transition-colors hover:bg-subtle hover:text-ink disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  )
}
