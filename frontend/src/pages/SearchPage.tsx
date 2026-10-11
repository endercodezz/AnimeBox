import { useSearchParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { ProviderSearchStatus } from '../api/types'
import { Icon } from '../components/icons'
import { PosterCard, PosterGrid, PosterGridSkeleton } from '../components/PosterCard'
import { Badge, ButtonLink, EmptyState, Notice, StatusDot } from '../components/ui'
import { cx } from '../lib/cx'
import { routes } from '../lib/routes'
import { useResource } from '../lib/useResource'

function ProviderStrip({ providers }: { providers: ProviderSearchStatus[] }) {
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Ответы источников">
      {providers.map((p) => (
        <li
          key={p.source}
          title={p.error || undefined}
          className={cx(
            'tabular inline-flex h-8 items-center gap-2 rounded-lg border px-2.5 text-[0.8rem]',
            p.ok ? 'border-line bg-ink-2 text-fog' : 'border-danger/25 bg-danger/[0.06] text-danger',
          )}
        >
          <span className={cx('size-1.5 rounded-full', p.ok ? (p.count ? 'bg-offline' : 'bg-dim') : 'bg-danger')} />
          <span className="font-semibold text-paper/90">{p.label}</span>
          {p.ok ? (
            <span>
              {p.count} · {((p.latency_ms ?? 0) / 1000).toFixed(1).replace('.', ',')} с
            </span>
          ) : (
            <span>{p.timed_out ? 'не ответил вовремя' : 'ошибка'}</span>
          )}
        </li>
      ))}
    </ul>
  )
}

export function SearchPage() {
  const [params, setParams] = useSearchParams()
  const query = (params.get('q') || '').trim()
  const source = params.get('source') || ''
  const providers = useResource((signal) => api.providers().then((list) => (signal.aborted ? [] : list)), [])
  const results = useResource((signal) => api.search(query, source || undefined, signal), [query, source], Boolean(query))
  const enabled = (providers.data ?? []).filter((p) => p.enabled)
  const data = results.data
  const failed = data?.providers.filter((p) => !p.ok) ?? []

  function pickSource(next: string) {
    const nextParams = new URLSearchParams(params)
    if (next) nextParams.set('source', next)
    else nextParams.delete('source')
    setParams(nextParams, { replace: true })
  }

  return (
    <div className="page space-y-7">
      <header className="flex flex-col gap-4">
        <div>
          <h1 className="display text-[1.7rem] font-semibold sm:text-[2rem]">{query ? `«${query}»` : 'Поиск'}</h1>
          {!query && <p className="mt-2 text-fog">Введите название в строке поиска вверху. Ищем сразу во всех включённых источниках.</p>}
        </div>
        <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 sm:mx-0 sm:flex-wrap sm:px-0" role="radiogroup" aria-label="Источник">
          {[{ id: '', label: 'Все включённые', status: null as null | (typeof enabled)[number]['status'] }, ...enabled.map((p) => ({ id: p.id, label: p.label, status: p.status }))].map((option) => (
            <button
              key={option.id || 'all'}
              type="button"
              role="radio"
              aria-checked={source === option.id}
              onClick={() => pickSource(option.id)}
              className={cx(
                'inline-flex h-9 shrink-0 items-center gap-2 rounded-full border px-3.5 text-[0.85rem] font-semibold transition-colors',
                source === option.id ? 'border-violet/60 bg-violet/16 text-paper' : 'border-line text-fog hover:border-white/15 hover:text-paper',
              )}
            >
              {option.status && <StatusDot status={option.status} />}
              {option.label}
            </button>
          ))}
        </div>
      </header>

      {!query && (
        <EmptyState icon="search" title="Начните с названия">
          Поиск работает по русским и английским названиям. Нажмите <kbd className="rounded border border-line px-1">/</kbd>, чтобы перейти к строке поиска.
        </EmptyState>
      )}

      {query && results.loading && (
        <div aria-busy="true">
          <p className="mb-5 flex items-center gap-2 text-[0.9rem] text-fog">
            <Icon name="pulse" size={16} className="text-violet-text" /> Опрашиваем источники…
          </p>
          <PosterGridSkeleton />
        </div>
      )}

      {query && results.error && !results.loading ? (
        <Notice title="Поиск не выполнен" action={<button type="button" className="font-bold" onClick={results.reload}>Повторить</button>}>
          {errorMessage(results.error)}
        </Notice>
      ) : null}

      {data && !results.loading && (
        <>
          <ProviderStrip providers={data.providers} />
          {failed.length > 0 && data.results.length > 0 && (
            <p className="text-[0.85rem] text-fog">
              {failed.map((p) => p.label).join(', ')} сейчас не ответил{failed.length > 1 ? 'и' : ''} — показаны результаты остальных источников.
            </p>
          )}
          {data.results.length > 0 ? (
            <PosterGrid className="enter">
              {data.results.map((item) => (
                <PosterCard
                  key={item.id}
                  to={routes.anime(item.id)}
                  title={item.title}
                  poster={item.poster}
                  meta={item.year ? `${item.year}` : undefined}
                  badge={<Badge className="bg-black/65 text-white/85 backdrop-blur">{item.source_label || item.source}</Badge>}
                />
              ))}
            </PosterGrid>
          ) : failed.length === data.providers.length ? (
            <EmptyState
              icon="alert"
              title="Источники не ответили"
              action={
                <>
                  <ButtonLink to={routes.settings('providers')} icon="settings">
                    Проверить источники
                  </ButtonLink>
                </>
              }
            >
              Возможно, нет подключения к интернету или сайты недоступны из вашей сети. Скачанные серии по-прежнему доступны в библиотеке.
            </EmptyState>
          ) : (
            <EmptyState icon="search" title="Ничего не найдено">
              Попробуйте другое написание или оригинальное название. {source && 'Можно также искать во всех источниках сразу.'}
            </EmptyState>
          )}
        </>
      )}
    </div>
  )
}
