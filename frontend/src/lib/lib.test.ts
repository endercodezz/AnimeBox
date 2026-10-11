import { describe, expect, it } from 'vitest'
import { episodesLabel, formatBytes, formatTime, progressRatio } from './format'
import { canonicalId } from './ids'
import { routes } from './routes'

describe('format', () => {
  it('formats time like a player', () => {
    expect(formatTime(0)).toBe('0:00')
    expect(formatTime(75)).toBe('1:15')
    expect(formatTime(3725)).toBe('1:02:05')
    expect(formatTime(Number.NaN)).toBe('0:00')
  })

  it('formats sizes with Russian units', () => {
    expect(formatBytes(512)).toBe('512 Б')
    expect(formatBytes(1536)).toBe('1,5 КБ')
    expect(formatBytes(110 * 1024 * 1024)).toBe('110 МБ')
    expect(formatBytes(null)).toBe('—')
  })

  it('pluralises episodes', () => {
    expect(episodesLabel(1)).toBe('1 серия')
    expect(episodesLabel(3)).toBe('3 серии')
    expect(episodesLabel(11)).toBe('11 серий')
    expect(episodesLabel(22)).toBe('22 серии')
  })

  it('clamps progress', () => {
    expect(progressRatio(30, 60)).toBe(0.5)
    expect(progressRatio(90, 60)).toBe(1)
    expect(progressRatio(10, null)).toBe(0)
  })
})

describe('ids', () => {
  it('matches the backend canonical form for both spellings', () => {
    expect(canonicalId('animego:/anime/keyon-2512')).toBe('animego:%2Fanime%2Fkeyon-2512')
    expect(canonicalId('animego:%2Fanime%2Fkeyon-2512')).toBe('animego:%2Fanime%2Fkeyon-2512')
    expect(canonicalId('anilibria:id:762')).toBe('anilibria:id%3A762')
    expect(canonicalId("x:it's(1)")).toBe('x:it%27s%281%29') // Python quote() escapes these too
    expect(canonicalId('no-colon')).toBe('no-colon')
  })
})

describe('routes', () => {
  it('encodes ids once for the router', () => {
    expect(routes.anime('animego:%2Fanime%2Fx')).toBe('/anime/animego%3A%252Fanime%252Fx')
    expect(routes.player('animego:%2Fanime%2Fx', { episode: 3, voiceover: 'AniLibria', t: 61.7 })).toBe(
      '/player/animego%3A%252Fanime%252Fx?episode=3&voiceover=AniLibria&t=61',
    )
    expect(routes.player('a:b', { episode: 1, local: 9 })).toBe('/player/a%3Ab?episode=1&local=9')
    expect(routes.search('врата', 'animego')).toBe('/search?q=%D0%B2%D1%80%D0%B0%D1%82%D0%B0&source=animego')
  })
})
