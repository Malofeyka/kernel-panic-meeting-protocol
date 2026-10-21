import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { UploadPage } from './UploadPage'

const audioInput = (container: HTMLElement) =>
  container.querySelector<HTMLInputElement>('input[type=file][accept*=".mp3"]')!

describe('UploadPage', () => {
  it('без аудио кнопка неактивна и объясняет почему', () => {
    render(<UploadPage onStarted={vi.fn()} onOpen={vi.fn()} />)
    expect(screen.getByRole('button', { name: /Сформировать проект протокола/ })).toBeDisabled()
    expect(screen.getByText('Добавьте аудиозапись совещания')).toBeInTheDocument()
  })

  it('неверный формат аудио — ошибка в строке файла', async () => {
    const user = userEvent.setup({ applyAccept: false })
    const { container } = render(<UploadPage onStarted={vi.fn()} onOpen={vi.fn()} />)
    await user.upload(audioInput(container), new File(['x'], 'запись.aiff'))
    expect(
      screen.getByText('Формат .aiff не подходит. Нужен MP3, WAV, M4A, OGG, FLAC или видеозапись.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Сформировать проект протокола/ })).toBeDisabled()
    expect(screen.getByText('Уберите или замените файлы с ошибками')).toBeInTheDocument()
  })

  it('с корректным аудио можно начинать', async () => {
    const user = userEvent.setup()
    const { container } = render(<UploadPage onStarted={vi.fn()} onOpen={vi.fn()} />)
    await user.upload(audioInput(container), new File(['x'], 'совещание.mp3'))
    expect(screen.getByText('совещание.mp3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Сформировать проект протокола/ })).toBeEnabled()
  })

  it('пачка файлов: в выборе только подходящие поля, чужой формат — ошибка', () => {
    const { container } = render(<UploadPage onStarted={vi.fn()} onOpen={vi.fn()} />)
    const files = [
      new File(['x'], 'запись.wav'),
      new File(['x'], 'справка.docx'),
      new File(['x'], 'видео.aiff'),
    ]
    fireEvent.drop(container.firstElementChild!, { dataTransfer: { files, types: ['Files'] } })

    const select = screen.getByRole('combobox', { name: 'Что за файл справка.docx' })
    const options = within(select)
      .getAllByRole('option')
      .map((o) => o.textContent)
    expect(options).not.toContain('Аудиозапись совещания')
    expect(options).toContain('Шаблон протокола')
    expect(screen.queryByRole('combobox', { name: 'Что за файл видео.aiff' })).toBeNull()
    expect(screen.getByText(/Формат \.aiff не поддерживается/)).toBeInTheDocument()
    expect(screen.getByText('Уберите файлы неподдерживаемого формата')).toBeInTheDocument()
  })
})
