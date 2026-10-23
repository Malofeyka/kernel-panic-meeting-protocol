import { cx } from '@/lib/cx'

export function Header({ onHome, wide }: { onHome: () => void; wide: boolean }) {
  return (
    <header className="border-b border-line bg-surface">
      <div
        className={cx(
          'mx-auto flex h-16 items-center px-6',
          wide ? 'max-w-[1280px]' : 'max-w-[880px]',
        )}
      >
        <button
          type="button"
          onClick={onHome}
          className="flex cursor-pointer items-center gap-3 rounded-md text-[17px] font-semibold"
        >
          <img src="/favicon.svg" alt="" className="size-8" />
          Протоколы совещаний
        </button>
      </div>
    </header>
  )
}
