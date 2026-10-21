import { useLayoutEffect, useRef, type TextareaHTMLAttributes } from 'react'

const fit = (el: HTMLTextAreaElement) => {
  el.style.height = 'auto'
  el.style.height = `${el.scrollHeight + 2}px`
}

/** Многострочное поле, растущее по высоте текста: правка текста «прямо в документе» */
export function AutoTextarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const ref = useRef<HTMLTextAreaElement>(null)
  useLayoutEffect(() => {
    if (ref.current) fit(ref.current)
  }, [props.value])
  // Ширина меняется (поворот экрана, сужение окна) — меняется и число строк
  useLayoutEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return
    let width = el.clientWidth
    const ro = new ResizeObserver(() => {
      if (el.clientWidth === width) return
      width = el.clientWidth
      fit(el)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return <textarea ref={ref} rows={1} {...props} style={{ resize: 'none', ...props.style }} />
}
