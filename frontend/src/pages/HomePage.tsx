import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { WatchHistory } from '../api/types'
import { ContinueCard } from '../components/ContinueCard'
import { Icon } from '../components/icons'
import { PosterCard, PosterGrid } from '../components/PosterCard'
import { ButtonLink, EmptyState, Notice, SectionHeader, Skeleton } from '../components/ui'
import { episodesLabel, formatBytes, formatTime, progressRatio, relativeDate } from '../lib/format'
import { continueTarget, routes } from '../lib/routes'
import { useResource } from '../lib/useResource'

function Spotlight({ item }: { item: WatchHistory }) {
  const ratio = progressRatio(item.progress_seconds, item.duration_seconds)
  return (
    <section className="enter relative isolate overflow-hidden rounded-[22px] border border-line">
      {item.poster && (
        <img src={item.poster} alt="" aria-hidden="true" referrerPolicy="no-referrer" className="absolute inset-0 -z-20 h-full w-full scale-110 object-cover opacity-60 blur-[2px]" />
      )}
      <div className="scrim-left absolute inset-0 -z-10" />
      <div className="flex min-h-[300px] flex-col justify-end gap-5 p-6 sm:min-h-[340px] sm:p-10">
        <div className="max-w-2xl">
          <p className="eyebrow text-violet-text">Продолжить просмотр</p>
          <h1 className="display mt-3 text-[2rem] font-semibold leading-[1.05] sm:text-[2.8rem]">{item.anime_title}</h1>
          <p className="tabular mt-3 text-[0.95rem] text-paper/80">
            Серия {item.episode}
            {item.voiceover ? ` · ${item.voiceover}` : ''} · {formatTime(item.progress_seconds)}
            {item.duration_seconds ? ` из ${formatTime(item.duration_seconds)}` : ''}
          </p>
          <div className="mt-3 h-1 max-w-sm overflow-hidden rounded-full bg-white/15">
            <div className="h-full bg-violet" style={{ width: `${Math.round(ratio * 100)}%` }} />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <ButtonLink to={continueTarget(item)} variant="primary" size="lg" icon="play">
            Продолжить
          </ButtonLink>
          <ButtonLink to={routes.anime(item.anime_external_id)} size="lg">
            Все серии
          </ButtonLink>
        </div>
      </div>
    </section>
  )
}

function QuickSearch({ prominent }: { prominent?: boolean }) {
  const navigate = useNavigate()
  const [value, setValue] = useState('')
  function submit(event: FormEvent) {
    event.preventDefault()
    if (value.trim()) navigate(routes.search(value.trim()))
  }
  return (
    <form onSubmit={submit} role="search" className={prominent ? 'enter' : ''}>
      <label className="relative block">
        <span className="sr-only">Название аниме</span>
        <Icon name="search" size={22} className="pointer-events-none absolute left-5 top-1/2 -translate-y-1/2 text-violet-text" />
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Например: Врата Штейна"
          maxLength={200}
          className="h-16 w-full rounded-2xl border border-line bg-ink-2 pl-14 pr-32 text-[1.05rem] outline-none transition placeholder:text-dim focus:border-violet/60"
        />
        <button type="submit" className="absolute right-2.5 top-1/2 h-11 -translate-y-1/2 rounded-xl bg-violet px-5 font-semibold text-white hover:bg-violet-hi">
          Найти
        </button>
      </label>
    </form>
  )
}

export function HomePage() {
  const feed = useResource((signal) => api.home(signal), [])
  const data = feed.data
  const [spotlight, ...restContinue] = data?.continue_watching ?? []
  const continueIds = new Set(data?.continue_watching.map((h) => h.id))
  const recent = (data?.recently_watched ?? []).filter((h) => !continueIds.has(h.id))
  const empty = data && !data.continue_watching.length && !data.recently_watched.length && !data.recently_downloaded.length

  return (
    <div className="page space-y-12">
      {feed.error ? <Notice title="Главная не загрузилась">{errorMessage(feed.error)}</Notice> : null}

      {feed.loading && !data && (
        <div className="space-y-6">
          <Skeleton className="h-[320px] rounded-[22px]" />
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-[118px] rounded-[var(--radius-card)]" />
            ))}
          </div>
        </div>
      )}

      {spotlight ? (
        <Spotlight item={spotlight} />
      ) : (
        data && (
          <section className="enter mx-auto max-w-3xl pt-6 text-center sm:pt-12">
            <h1 className="display text-[2rem] font-semibold leading-tight sm:text-[2.6rem]">Что смотрим?</h1>
            <p className="mx-auto mt-3 max-w-lg text-fog">
              Найдите тайтл, выберите озвучку и смотрите онлайн или скачайте серии, чтобы смотреть без интернета.
            </p>
            <div className="mt-7 text-left">
              <QuickSearch prominent />
            </div>
          </section>
        )
      )}

      {restContinue.length > 0 && (
        <section>
          <SectionHeader title="Продолжить просмотр" />
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {restContinue.map((item) => (
              <ContinueCard key={item.id} item={item} />
            ))}
          </div>
        </section>
      )}

      {spotlight && (
        <section>
          <QuickSearch />
        </section>
      )}

      {data && data.recently_downloaded.length > 0 && (
        <section>
          <SectionHeader title="Недавно скачано" action={<Link to={routes.library()} className="text-[0.88rem] font-semibold text-violet-text hover:text-paper">Вся библиотека</Link>} />
          <PosterGrid>
            {data.recently_downloaded.map((item) => (
              <PosterCard
                key={item.id}
                to={routes.anime(item.id)}
                title={item.title}
                poster={item.poster}
                meta={`${episodesLabel(item.episode_count)} · ${formatBytes(item.size_bytes)}`}
              />
            ))}
          </PosterGrid>
        </section>
      )}

      {recent.length > 0 && (
        <section>
          <SectionHeader title="Недавно просмотрено" />
          <PosterGrid>
            {recent.map((item) => (
              <PosterCard
                key={item.id}
                to={routes.anime(item.anime_external_id)}
                title={item.anime_title}
                poster={item.poster}
                progress={item.completed ? 1 : progressRatio(item.progress_seconds, item.duration_seconds)}
                meta={`Серия ${item.episode} · ${relativeDate(item.updated_at)}`}
              />
            ))}
          </PosterGrid>
        </section>
      )}

      {empty && (
        <EmptyState icon="film" title="Здесь появится ваша история">
          Начните просмотр — AnimeBox запомнит, на какой минуте вы остановились. Скачанные серии будут ждать в библиотеке.
        </EmptyState>
      )}
    </div>
  )
}
