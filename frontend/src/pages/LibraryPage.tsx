import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { LibraryAnime } from '../api/types'
import { AnimeCard } from '../components/AnimeCard'

export function LibraryPage() {
  const [items, setItems] = useState<LibraryAnime[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.library().then(setItems).catch((err) => setError(err instanceof Error ? err.message : 'Библиотека недоступна')).finally(() => setLoading(false))
  }, [])

  const episodeCount = items.reduce((sum, item) => sum + item.episode_count, 0)

  return (
    <div className="animate-rise space-y-8">
      <header className="flex flex-col gap-5 border-b border-white/8 pb-7 sm:flex-row sm:items-end sm:justify-between">
        <div><p className="eyebrow">На этом устройстве</p><h1 className="mt-2 font-display text-4xl font-extrabold tracking-[-0.04em] sm:text-5xl">Моя библиотека</h1><p className="mt-3 max-w-xl text-fog">Скачанные тайтлы доступны без подключения к интернету.</p></div>
        <div className="flex gap-3">
          <div className="surface rounded-2xl px-5 py-3"><p className="text-2xl font-extrabold">{items.length}</p><p className="text-xs uppercase tracking-wider text-fog">тайтлов</p></div>
          <div className="surface rounded-2xl px-5 py-3"><p className="text-2xl font-extrabold text-violet-soft">{episodeCount}</p><p className="text-xs uppercase tracking-wider text-fog">серий</p></div>
        </div>
      </header>
      {loading && <p className="text-fog">Сканируем библиотеку…</p>}
      {error && <p className="rounded-xl border border-danger/20 bg-danger/8 p-4 text-danger">{error}</p>}
      {!loading && !items.length && <div className="surface rounded-3xl px-6 py-16 text-center"><div className="mx-auto grid size-14 place-items-center rounded-2xl bg-amber/12 text-2xl text-violet-soft">↓</div><h2 className="mt-5 font-display text-xl font-bold">Библиотека пуста</h2><p className="mt-2 text-sm text-fog">Найдите аниме и загрузите первую серию.</p></div>}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-7">
        {items.map((item) => <AnimeCard key={item.id} id={item.id} title={item.title} poster={item.poster} year={item.year} source={item.source} subtitle={`${item.episode_count} эп.`} to={`/anime/${encodeURIComponent(item.id)}?local=1`} />)}
      </div>
    </div>
  )
}
