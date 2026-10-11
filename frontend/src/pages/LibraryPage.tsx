import { useMemo, useState } from 'react'
import { api, errorMessage } from '../api/client'
import type { LibraryAnime } from '../api/types'
import { Icon } from '../components/icons'
import { PosterCard, PosterGrid, PosterGridSkeleton } from '../components/PosterCard'
import { useToast } from '../components/toast'
import { Badge, Button, ButtonLink, ConfirmDialog, EmptyState, IconButton, Notice, Segmented } from '../components/ui'
import { episodesLabel, formatBytes } from '../lib/format'
import { routes } from '../lib/routes'
import { useResource } from '../lib/useResource'

type Sort = 'recent' | 'title' | 'size'

export function LibraryPage() {
  const toast = useToast()
  const items = useResource((signal) => api.library(signal), [])
  const stats = useResource(() => api.libraryStats(), [items.data])
  const [sort, setSort] = useState<Sort>('recent')
  const [filter, setFilter] = useState('')
  const [onlyUnwatched, setOnlyUnwatched] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<LibraryAnime | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [rescanning, setRescanning] = useState(false)

  const shown = useMemo(() => {
    const needle = filter.trim().toLocaleLowerCase('ru')
    const list = (items.data ?? []).filter(
      (item) => (!needle || item.title.toLocaleLowerCase('ru').includes(needle)) && (!onlyUnwatched || item.watched_count < item.episode_count),
    )
    const sorted = [...list]
    if (sort === 'title') sorted.sort((a, b) => a.title.localeCompare(b.title, 'ru'))
    if (sort === 'size') sorted.sort((a, b) => b.size_bytes - a.size_bytes)
    return sorted
  }, [items.data, filter, sort, onlyUnwatched])

  async function remove(item: LibraryAnime) {
    setDeleting(true)
    try {
      await api.deleteLibraryAnime(item.id)
      toast.show(`«${item.title}» удалён из библиотеки`)
      items.setData((list) => (list ?? []).filter((x) => x.id !== item.id))
    } catch (err) {
      toast.show(errorMessage(err), 'error')
    } finally {
      setDeleting(false)
      setPendingDelete(null)
    }
  }

  async function rescan() {
    setRescanning(true)
    try {
      const result = await api.rescanLibrary()
      const changes = result.imported + result.removed_missing
      toast.show(
        changes
          ? `Найдено новых серий: ${result.imported}, убрано записей без файлов: ${result.removed_missing}`
          : 'Библиотека совпадает с файлами на диске',
        'info',
      )
      items.reload()
    } catch (err) {
      toast.show(errorMessage(err), 'error')
    } finally {
      setRescanning(false)
    }
  }

  const s = stats.data
  const usedShare = s && s.disk_total ? s.size_bytes / s.disk_total : 0

  return (
    <div className="page space-y-7">
      <header className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="display text-[1.7rem] font-semibold sm:text-[2rem]">Библиотека</h1>
          <p className="mt-2 max-w-xl text-fog">Скачанные серии на этом устройстве. Они открываются без интернета.</p>
        </div>
        {s && (
          <div className="panel tabular flex items-center gap-5 px-4 py-3 text-[0.85rem]">
            <div>
              <p className="text-[1.05rem] font-bold">{s.titles}</p>
              <p className="text-fog">тайтлов</p>
            </div>
            <div>
              <p className="text-[1.05rem] font-bold">{s.episodes}</p>
              <p className="text-fog">серий</p>
            </div>
            <div className="min-w-[150px]">
              <p className="text-[1.05rem] font-bold">{formatBytes(s.size_bytes)}</p>
              <p className="text-fog">свободно {formatBytes(s.disk_free)}</p>
              <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-white/10" title="Доля диска, занятая библиотекой">
                <div className="h-full bg-offline" style={{ width: `${Math.max(2, Math.min(100, usedShare * 100))}%` }} />
              </div>
            </div>
          </div>
        )}
      </header>

      {items.error ? <Notice title="Библиотека недоступна">{errorMessage(items.error)}</Notice> : null}

      {(items.data?.length ?? 0) > 0 && (
        <div className="flex flex-wrap items-center gap-3">
          <label className="relative min-w-[220px] flex-1 sm:max-w-sm">
            <span className="sr-only">Фильтр по названию</span>
            <Icon name="search" size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-dim" />
            <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Фильтр по названию" className="field h-10 pl-9" />
          </label>
          <Segmented<Sort>
            label="Сортировка"
            value={sort}
            onChange={setSort}
            options={[
              { value: 'recent', label: 'Недавние' },
              { value: 'title', label: 'По названию' },
              { value: 'size', label: 'По размеру' },
            ]}
          />
          <Button size="sm" variant={onlyUnwatched ? 'primary' : 'secondary'} onClick={() => setOnlyUnwatched((v) => !v)} aria-pressed={onlyUnwatched}>
            Есть непросмотренные
          </Button>
          <Button size="sm" variant="ghost" icon="retry" loading={rescanning} onClick={() => void rescan()} className="ml-auto">
            Пересканировать
          </Button>
        </div>
      )}

      {items.loading && !items.data && <PosterGridSkeleton count={8} />}

      {items.data && items.data.length === 0 && (
        <EmptyState
          icon="library"
          title="Библиотека пуста"
          action={
            <>
              <ButtonLink to={routes.search()} variant="primary" icon="search">
                Найти аниме
              </ButtonLink>
              <Button icon="retry" loading={rescanning} onClick={() => void rescan()}>
                Пересканировать папку
              </Button>
            </>
          }
        >
          Откройте тайтл и нажмите «Скачать серию» или «Скачать сезон». Здесь появятся только серии, которые реально лежат на диске.
        </EmptyState>
      )}

      {items.data && items.data.length > 0 && shown.length === 0 && <p className="text-fog">Нет тайтлов, подходящих под фильтр.</p>}

      {shown.length > 0 && (
        <PosterGrid className="enter">
          {shown.map((item) => (
            <div key={item.id} className="group/item relative">
              <PosterCard
                to={routes.anime(item.id)}
                title={item.title}
                poster={item.poster}
                badge={
                  <>
                    <Badge tone="offline" className="bg-black/70 backdrop-blur">
                      <Icon name="offline" size={12} />
                      {item.episode_count}
                    </Badge>
                    {item.missing_count > 0 && (
                      <Badge tone="warn" className="bg-black/70 backdrop-blur">
                        −{item.missing_count}
                      </Badge>
                    )}
                  </>
                }
                meta={
                  <span className="tabular">
                    {episodesLabel(item.episode_count)} · {formatBytes(item.size_bytes)}
                    {item.watched_count > 0 && ` · просмотрено ${item.watched_count}`}
                  </span>
                }
              />
              <IconButton
                icon="trash"
                label={`Удалить «${item.title}» из библиотеки`}
                size={34}
                onClick={() => setPendingDelete(item)}
                className="absolute right-2 top-2 bg-black/70 text-paper opacity-0 backdrop-blur transition-opacity group-hover/item:opacity-100 focus-visible:opacity-100 hover:text-danger"
              />
            </div>
          ))}
        </PosterGrid>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        title={`Удалить «${pendingDelete?.title ?? ''}»?`}
        confirmLabel="Удалить файлы"
        busy={deleting}
        onConfirm={() => pendingDelete && void remove(pendingDelete)}
        onCancel={() => setPendingDelete(null)}
      >
        {pendingDelete && (
          <>
            С диска будут удалены {episodesLabel(pendingDelete.episode_count)} ({formatBytes(pendingDelete.size_bytes)}), постер и metadata.json. История
            просмотра сохранится, тайтл можно будет скачать снова.
          </>
        )}
      </ConfirmDialog>
    </div>
  )
}
