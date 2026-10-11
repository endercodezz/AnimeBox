// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from '../api/client'
import { EpisodeGrid, type EpisodeState } from './EpisodeGrid'
import { EmptyState, ProgressBar } from './ui'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('EpisodeGrid', () => {
  const episodes = [1, 2, 3].map((n) => ({ ordinal: n, season: 1, title: `Episode ${n}` }))
  const states = new Map<number, EpisodeState>([
    [1, { progress: 1, completed: true, downloaded: true, missing: false, queued: false }],
    [2, { progress: 0.4, completed: false, downloaded: false, missing: false, queued: true }],
  ])

  it('describes each episode state for assistive technology and selects on click', () => {
    const onSelect = vi.fn()
    render(<EpisodeGrid episodes={episodes} states={states} selected={2} onSelect={onSelect} />)
    expect(screen.getByRole('button', { name: /Серия 1, просмотрена, доступна офлайн/ })).toBeTruthy()
    const second = screen.getByRole('button', { name: /Серия 2, просмотрено 40%, в очереди загрузки/ })
    expect(second.getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(screen.getByRole('button', { name: 'Серия 3' }))
    expect(onSelect).toHaveBeenCalledWith(3)
  })
})

describe('ui primitives', () => {
  it('clamps progress values', () => {
    render(<ProgressBar value={140} label="test" />)
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('100')
  })

  it('renders empty states with an action', () => {
    render(<EmptyState icon="library" title="Библиотека пуста" action={<button type="button">Найти</button>}>Подсказка</EmptyState>)
    expect(screen.getByRole('heading', { name: 'Библиотека пуста' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Найти' })).toBeTruthy()
  })
})

describe('api client', () => {
  it('surfaces structured backend errors', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: { code: 'provider_timeout', message: 'details timed out', stage: 'details', source: 'animego' } }), {
        status: 504,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const error = await api.anime('animego:%2Fanime%2Fx').catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect([error.status, error.code, error.stage, error.source, error.message]).toEqual([504, 'provider_timeout', 'details', 'animego', 'details timed out'])
  })

  it('reports an unreachable backend in plain language', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    const error = await api.health().catch((e) => e)
    expect(error.code).toBe('offline')
    expect(error.message).toMatch(/AnimeBox не отвечает/)
  })

  it('sends anime ids as query parameters', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('[]', { status: 200 }))
    await api.libraryEpisodes('animego:%2Fanime%2Fx')
    expect(spy.mock.calls[0][0]).toBe('/api/library/episodes?id=animego%3A%252Fanime%252Fx')
  })
})
