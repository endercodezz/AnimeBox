import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { SearchResult, WatchHistory } from '../api/types'
import heroArt from '../assets/hero.png'
import { AnimeCard } from '../components/AnimeCard'

export function SearchPage() {
  const [q, setQ] = useState('')
  const [source, setSource] = useState('')
  const [sources, setSources] = useState<string[]>([])
  const [results, setResults] = useState<SearchResult[]>([])
  const [history, setHistory] = useState<WatchHistory[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.sources().then((s) => setSources(s.map((x) => x.id))).catch(() => {})
    api.history().then(setHistory).catch(() => {})
  }, [])

  async function onSearch(e: React.FormEvent) {
    e.preventDefault()
    if (!q.trim()) return
    setLoading(true)
    setError(null)
    try {
      const data = await api.search(q.trim(), source || undefined)
      setResults(data)
      if (!data.length) setError('Ничего не найдено. Измените запрос или выберите другой источник.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Поиск недоступен')
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-12">
      <section className="projector-beam surface animate-rise relative isolate min-h-[390px] overflow-hidden rounded-[28px] px-5 py-8 sm:px-9 sm:py-10 lg:flex lg:min-h-[450px] lg:items-center lg:px-14">
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(circle_at_78%_40%,rgba(139,92,246,0.18),transparent_31%),linear-gradient(90deg,rgba(8,7,13,0.99)_0%,rgba(8,7,13,0.92)_46%,rgba(8,7,13,0.2)_100%)]" />
        <img
          src={heroArt}
          alt=""
          className="pointer-events-none absolute -right-10 bottom-6 -z-10 w-[310px] rotate-3 opacity-25 drop-shadow-[0_35px_80px_rgba(139,92,246,0.45)] sm:right-2 sm:w-[390px] sm:opacity-45 lg:right-[5%] lg:w-[470px] lg:opacity-75"
        />

        <div className="relative z-10 max-w-3xl space-y-6">
          <div className="space-y-3">
            <p className="eyebrow">Личная коллекция · без облака</p>
            <h1 className="max-w-2xl font-display text-4xl font-extrabold leading-[0.98] tracking-[-0.055em] sm:text-6xl lg:text-7xl">
              Ваше аниме.
              <span className="block bg-gradient-to-r from-violet-soft to-[#d8c7ff] bg-clip-text text-transparent">
                Всегда рядом.
              </span>
            </h1>
            <p className="max-w-xl text-sm leading-6 text-fog sm:text-base">
              Найдите тайтл, выберите озвучку и сохраните серии на устройство. В дороге интернет не понадобится.
            </p>
          </div>

          <form onSubmit={onSearch} className="surface flex max-w-3xl flex-col gap-2 rounded-2xl p-2 sm:flex-row">
            <label className="flex min-w-0 flex-1 items-center gap-3 px-3">
              <span className="text-lg text-violet-soft" aria-hidden="true">⌕</span>
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Название аниме"
                className="min-w-0 flex-1 bg-transparent py-3 text-base text-paper outline-none placeholder:text-fog/45"
                autoFocus
                aria-label="Название аниме"
              />
            </label>
            <select
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="rounded-xl border border-white/8 bg-ink-3 px-3 py-3 text-sm font-semibold text-paper sm:max-w-40"
              aria-label="Источник"
            >
              <option value="">Все источники</option>
              {sources.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <button type="submit" disabled={loading} className="btn-primary min-w-28">
              {loading ? 'Ищем…' : 'Найти'}
            </button>
          </form>
          {error && <p className="rounded-xl border border-danger/20 bg-danger/8 px-4 py-3 text-sm text-danger">{error}</p>}

          <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs font-semibold uppercase tracking-[0.12em] text-fog/65">
            <span>◉ Локальный просмотр</span><span>↓ Загрузка сезонов</span><span>⌁ 8 источников</span>
          </div>
        </div>
      </section>

      {results.length > 0 && (
        <section className="animate-rise space-y-5">
          <div className="flex items-end justify-between gap-4">
            <div><p className="eyebrow">Каталог</p><h2 className="section-title">Результаты поиска</h2></div>
            <span className="text-sm text-fog">Найдено: {results.length}</span>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-7">
            {results.map((item) => (
              <AnimeCard key={item.id} id={item.id} title={item.title} poster={item.poster} year={item.year} source={item.source} />
            ))}
          </div>
        </section>
      )}

      {!results.length && history.length > 0 && (
        <section className="space-y-5">
          <div className="flex items-end justify-between gap-4">
            <div><p className="eyebrow">С этого места</p><h2 className="section-title">Продолжить просмотр</h2></div>
            <Link to="/library" className="text-sm font-bold text-violet-soft hover:text-paper">Вся библиотека →</Link>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {history.slice(0, 6).map((h) => {
              const pct = h.duration_seconds ? Math.min(100, Math.round((h.progress_seconds / h.duration_seconds) * 100)) : 0
              return (
                <Link
                  key={h.id}
                  to={`/player/${encodeURIComponent(h.anime_external_id)}?episode=${h.episode}&season=${h.season}${h.local_episode_id ? `&local=${h.local_episode_id}` : ''}`}
                  className="surface group flex gap-4 rounded-2xl p-3 transition hover:border-amber/40 hover:bg-ink-3/80"
                >
                  <div className="h-24 w-17 shrink-0 overflow-hidden rounded-xl bg-ink-4">
                    {h.poster ? <img src={h.poster} alt="" className="h-full w-full object-cover transition group-hover:scale-105" /> : <div className="h-full bg-amber/10" />}
                  </div>
                  <div className="flex min-w-0 flex-1 flex-col justify-center gap-2">
                    <div><p className="truncate font-display font-bold">{h.anime_title}</p><p className="mt-1 text-xs font-semibold uppercase tracking-wider text-fog">Сезон {h.season} · Серия {h.episode}</p></div>
                    <div className="h-1 overflow-hidden rounded-full bg-white/8"><div className="h-full bg-amber" style={{ width: `${pct}%` }} /></div>
                  </div>
                  <span className="self-center text-violet-soft transition group-hover:translate-x-1">▶</span>
                </Link>
              )
            })}
          </div>
        </section>
      )}

      {!results.length && !history.length && !loading && (
        <section className="grid gap-4 md:grid-cols-3">
          {[
            ['01', 'Найдите тайтл', 'Ищите сразу по нескольким открытым источникам.'],
            ['02', 'Выберите озвучку', 'AnimeBox запомнит ваши приоритеты.'],
            ['03', 'Возьмите с собой', 'Скачайте серии и смотрите полностью офлайн.'],
          ].map(([number, title, text]) => (
            <div key={number} className="surface rounded-2xl p-5">
              <span className="font-display text-sm font-extrabold text-amber">{number}</span>
              <h2 className="mt-5 font-display text-lg font-bold">{title}</h2>
              <p className="mt-2 text-sm leading-6 text-fog">{text}</p>
            </div>
          ))}
        </section>
      )}
    </div>
  )
}
