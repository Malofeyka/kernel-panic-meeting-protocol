import { useId, useState, type Dispatch, type ReactNode } from 'react'
import { PlusIcon, XIcon } from '@phosphor-icons/react'
import type { ActionItem, AgendaItem, Attendee, ProtocolDraft } from '@/api'
import { cx } from '@/lib/cx'
import { isoToRu, ruToIso } from '@/lib/dates'
import { actionNumber, decisionNumber } from '@/lib/protocol'
import { AutoTextarea } from '@/ui/AutoTextarea'
import { IconButton } from '@/ui/Button'
import type { EditorAction } from './draftReducer'

interface Props {
  draft: ProtocolDraft
  dispatch: Dispatch<EditorAction>
  /** Показать фрагмент стенограммы, откуда взят пункт */
  onQuote: (quote: string, start: number | null) => void
}

/** Поле, которое выглядит как текст документа, а при наведении и фокусе — как поле ввода */
const inline =
  'min-w-0 rounded-[6px] border border-transparent bg-transparent px-2 py-1 text-ink ' +
  'transition-colors placeholder:text-ink-3 hover:border-line-strong focus:border-primary ' +
  'focus:bg-surface focus:outline-none focus-visible:outline-none focus:ring-3 focus:ring-primary/15'

/** Незаполненное обязательное поле поручения: видно сразу, без отдельного значка */
const missing = 'bg-warning-soft placeholder:text-warning hover:border-warning/40'

export function ProtocolEditor({ draft, dispatch, onQuote }: Props) {
  const m = draft.metadata
  const people = useId()

  return (
    <article className="rounded-[var(--radius-card)] border border-line bg-surface px-6 py-8 sm:px-12 sm:py-10">
      <PeopleList id={people} attendees={m.attendees} />

      <header className="text-center">
        <p className="text-sm font-semibold tracking-[0.12em] text-ink-2 uppercase">Протокол</p>
        <AutoTextarea
          id="meta-title"
          aria-label="Наименование совещания"
          className={cx(inline, 'w-full', 'mt-1 text-center text-[22px] leading-8 font-semibold')}
          value={m.meeting_title}
          onChange={(e) => dispatch({ type: 'meta', patch: { meeting_title: e.target.value } })}
        />
        <div className="mt-1 flex items-center justify-center gap-2 text-ink-2">
          <input
            type="date"
            aria-label="Дата совещания"
            className={cx(inline, 'w-[150px] tabular-nums')}
            value={ruToIso(m.meeting_date)}
            onChange={(e) =>
              e.target.value &&
              dispatch({ type: 'meta', patch: { meeting_date: isoToRu(e.target.value) } })
            }
          />
          <span>№</span>
          <input
            aria-label="Номер протокола"
            placeholder="без номера"
            className={cx(inline, 'w-32')}
            value={m.protocol_number ?? ''}
            onChange={(e) =>
              dispatch({ type: 'meta', patch: { protocol_number: e.target.value || null } })
            }
          />
        </div>
      </header>

      <dl className="mt-8 grid items-baseline gap-x-4 gap-y-1 border-y border-line py-5 sm:grid-cols-[150px_minmax(0,1fr)]">
        <dt className="text-ink-3">Председатель</dt>
        <dd>
          <input
            aria-label="Председатель"
            list={people}
            placeholder="Укажите председателя"
            className={cx(inline, 'w-full', !m.chairperson && missing)}
            value={m.chairperson ?? ''}
            onChange={(e) =>
              dispatch({ type: 'meta', patch: { chairperson: e.target.value || null } })
            }
          />
        </dd>
        <dt className="text-ink-3">Секретарь</dt>
        <dd>
          <input
            aria-label="Секретарь"
            list={people}
            placeholder="Укажите секретаря"
            className={cx(inline, 'w-full', !m.secretary && missing)}
            value={m.secretary ?? ''}
            onChange={(e) =>
              dispatch({ type: 'meta', patch: { secretary: e.target.value || null } })
            }
          />
        </dd>
        <dt className="pt-1.5 text-ink-3">Присутствовали</dt>
        <dd>
          <Attendees attendees={m.attendees} dispatch={dispatch} />
        </dd>
      </dl>

      {draft.agenda_items.length === 0 && (
        <p className="mt-8 text-ink-3">
          В записи не найдено принятых решений и поручений. Добавьте вопрос вручную.
        </p>
      )}

      <ol className="mt-8 flex flex-col gap-10">
        {draft.agenda_items.map((item, i) => (
          <Question
            key={i}
            item={item}
            index={i}
            people={people}
            dispatch={dispatch}
            onQuote={onQuote}
          />
        ))}
      </ol>

      <AddButton className="mt-8" onClick={() => dispatch({ type: 'itemAdd' })}>
        Добавить вопрос
      </AddButton>
    </article>
  )
}

function Question({
  item,
  index,
  people,
  dispatch,
  onQuote,
}: {
  item: AgendaItem
  index: number
  people: string
  dispatch: Dispatch<EditorAction>
  onQuote: Props['onQuote']
}) {
  const remove = () => {
    const empty = item.decisions.length === 0 && item.action_items.length === 0
    if (empty || window.confirm(`Удалить вопрос ${item.item_number} со всеми решениями?`))
      dispatch({ type: 'itemRemove', item: index })
  }
  return (
    <li id={`item-${item.item_number}`} className="rounded-[8px] transition-colors">
      <div className="group flex items-start gap-1">
        <span className="pt-1 text-[17px] leading-7 font-semibold tabular-nums">
          {item.item_number}.
        </span>
        <AutoTextarea
          aria-label={`Тема вопроса ${item.item_number}`}
          placeholder="Тема вопроса"
          className={cx(
            inline,
            'w-full',
            'text-[17px] leading-7 font-semibold',
            !item.topic && missing,
          )}
          value={item.topic}
          onChange={(e) =>
            dispatch({ type: 'item', item: index, patch: { topic: e.target.value } })
          }
        />
        <RemoveButton label={`Удалить вопрос ${item.item_number}`} onClick={remove} />
      </div>
      <div className="mt-0.5 flex items-baseline gap-1 pl-5 text-ink-2">
        <span className="shrink-0 text-ink-3">Докладчик:</span>
        <input
          aria-label={`Докладчик по вопросу ${item.item_number}`}
          list={people}
          placeholder="не указан"
          className={cx(inline, 'w-full', 'max-w-sm')}
          value={item.reporter ?? ''}
          onChange={(e) =>
            dispatch({ type: 'item', item: index, patch: { reporter: e.target.value || null } })
          }
        />
      </div>

      <p className="mt-5 text-sm font-semibold tracking-[0.06em] text-ink-2 uppercase">Решили</p>
      <ol className="mt-2 flex flex-col gap-1">
        {item.decisions.map((d, j) => (
          <li
            key={d.id ?? j}
            id={d.id ? `row-${d.id}` : undefined}
            className="rounded-[8px] transition-colors"
          >
            <div className="group flex items-start gap-1">
              <Num>{decisionNumber(item, j)}</Num>
              <div className="min-w-0 flex-1">
                <AutoTextarea
                  aria-label={`Решение ${decisionNumber(item, j)}`}
                  placeholder="Текст решения"
                  className={cx(inline, 'w-full', !d.text && missing)}
                  value={d.text}
                  onChange={(e) =>
                    dispatch({ type: 'decision', item: index, index: j, text: e.target.value })
                  }
                />
                <Quote quote={d.quote} start={d.source_start} onQuote={onQuote} />
              </div>
              <RemoveButton
                label={`Удалить решение ${decisionNumber(item, j)}`}
                onClick={() => dispatch({ type: 'decisionRemove', item: index, index: j })}
              />
            </div>
          </li>
        ))}
        {item.action_items.map((a, j) => (
          <ActionRow
            key={a.id ?? `new-${j}`}
            action={a}
            number={actionNumber(item, j)}
            people={people}
            onChange={(patch) => dispatch({ type: 'action', item: index, index: j, patch })}
            onRemove={() => dispatch({ type: 'actionRemove', item: index, index: j })}
            onQuote={onQuote}
          />
        ))}
      </ol>
      <div className="mt-2 flex flex-wrap gap-x-6 pl-11">
        <AddButton onClick={() => dispatch({ type: 'decisionAdd', item: index })}>
          Добавить решение
        </AddButton>
        <AddButton onClick={() => dispatch({ type: 'actionAdd', item: index })}>
          Добавить поручение
        </AddButton>
      </div>
    </li>
  )
}

function ActionRow({
  action: a,
  number,
  people,
  onChange,
  onRemove,
  onQuote,
}: {
  action: ActionItem
  number: string
  people: string
  onChange: (patch: Partial<ActionItem>) => void
  onRemove: () => void
  onQuote: Props['onQuote']
}) {
  const noDate = !a.due_date && !a.is_recurring
  return (
    <li id={a.id ? `row-${a.id}` : undefined} className="rounded-[8px] transition-colors">
      <div className="group flex items-start gap-1">
        <Num>{number}</Num>
        <div className="min-w-0 flex-1">
          <AutoTextarea
            aria-label={`Поручение ${number}`}
            placeholder="Текст поручения"
            className={cx(inline, 'w-full', !a.task && missing)}
            value={a.task}
            onChange={(e) => onChange({ task: e.target.value })}
          />
          <div className="mt-1 grid gap-x-4 gap-y-1 px-2 sm:grid-cols-[minmax(0,1fr)_auto]">
            <label className="flex min-w-0 flex-col sm:flex-row sm:items-baseline sm:gap-1">
              <span className="shrink-0 text-sm text-ink-3">Ответственный</span>
              <input
                list={people}
                placeholder="Укажите ответственного"
                className={cx(inline, 'w-full', 'text-[15px]', !a.assignee && missing)}
                value={a.assignee ?? ''}
                onChange={(e) => onChange({ assignee: e.target.value || null })}
              />
            </label>
            <label className="flex flex-col sm:flex-row sm:items-baseline sm:gap-1">
              <span className="shrink-0 text-sm text-ink-3">Срок</span>
              <input
                type="date"
                className={cx(inline, 'w-[150px] text-[15px] tabular-nums', noDate && missing)}
                value={ruToIso(a.due_date)}
                onChange={(e) =>
                  onChange({ due_date: e.target.value ? isoToRu(e.target.value) : null })
                }
              />
            </label>
          </div>
          {noDate && a.due_date_raw && (
            <p className="px-2 text-sm text-warning">Прозвучало: «{a.due_date_raw}»</p>
          )}
          <Quote quote={a.quote} start={a.source_start} onQuote={onQuote} />
        </div>
        <RemoveButton label={`Удалить поручение ${number}`} onClick={onRemove} />
      </div>
    </li>
  )
}

/** Цитата из стенограммы — чем подтверждён пункт; клик показывает её в стенограмме */
function Quote({
  quote,
  start,
  onQuote,
}: {
  quote: string | null
  start: number | null
  onQuote: Props['onQuote']
}) {
  if (!quote) return null
  return (
    <button
      type="button"
      onClick={() => onQuote(quote, start)}
      className="mt-0.5 block cursor-pointer px-2 text-left text-sm text-ink-3 italic hover:text-primary"
      title="Показать в стенограмме"
    >
      «{quote}»
    </button>
  )
}

function Attendees({
  attendees,
  dispatch,
}: {
  attendees: Attendee[]
  dispatch: Dispatch<EditorAction>
}) {
  const [name, setName] = useState('')
  const add = () => {
    dispatch({ type: 'attendeeAdd', name })
    setName('')
  }
  return (
    <ul className="flex flex-wrap items-center gap-x-1 gap-y-1">
      {attendees.map((p, i) => (
        <li
          key={`${p.full_name}-${i}`}
          className="group relative rounded-[6px] py-1 pr-6 pl-2 hover:bg-subtle"
          title={p.position ? `${p.full_name}, ${p.position}` : p.full_name}
        >
          {p.short_name || p.full_name}
          {i < attendees.length - 1 && ','}
          <IconButton
            label={`Убрать ${p.short_name || p.full_name}`}
            className="absolute top-1/2 right-0.5 size-5 -translate-y-1/2 opacity-0 group-hover:opacity-100 focus:opacity-100"
            onClick={() => dispatch({ type: 'attendeeRemove', index: i })}
          >
            <XIcon size={12} />
          </IconButton>
        </li>
      ))}
      <li>
        <input
          aria-label="Добавить участника"
          placeholder="+ добавить"
          className={cx(inline, 'w-40')}
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={add}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              add()
            }
          }}
        />
      </li>
    </ul>
  )
}

/** Подсказки для полей «Ответственный», «Докладчик» и т. п. — из списка участников */
function PeopleList({ id, attendees }: { id: string; attendees: Attendee[] }) {
  return (
    <datalist id={id}>
      {attendees.map((p) => (
        <option key={p.full_name} value={p.short_name || p.full_name}>
          {p.position ?? undefined}
        </option>
      ))}
    </datalist>
  )
}

function Num({ children }: { children: string }) {
  return <span className="w-10 shrink-0 pt-1 text-right text-ink-3 tabular-nums">{children}.</span>
}

function RemoveButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <IconButton
      label={label}
      onClick={onClick}
      className="mt-0.5 opacity-0 group-hover:opacity-100 focus:opacity-100"
    >
      <XIcon size={16} />
    </IconButton>
  )
}

function AddButton({
  children,
  className,
  onClick,
}: {
  children: ReactNode
  className?: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      className={cx(
        'inline-flex cursor-pointer items-center gap-1.5 py-1 text-[15px] text-primary hover:text-primary-hover',
        className,
      )}
      onClick={onClick}
    >
      <PlusIcon size={14} />
      {children}
    </button>
  )
}
