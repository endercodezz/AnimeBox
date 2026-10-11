import { useEffect, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { AppSettings, ProviderInfo } from '../api/types'
import { Icon } from '../components/icons'
import { useToast } from '../components/toast'
import { Badge, Button, IconButton, Notice, Segmented, Skeleton, StatusDot, Toggle } from '../components/ui'
import { cx } from '../lib/cx'
import { formatBytes, relativeDate } from '../lib/format'
import { setPrefs, usePrefs } from '../lib/prefs'
import { useResource } from '../lib/useResource'

const SECTIONS = [
  { id: 'playback', label: 'Воспроизведение' },
  { id: 'downloads', label: 'Загрузки' },
  { id: 'providers', label: 'Источники' },
  { id: 'network', label: 'Сеть' },
  { id: 'storage', label: 'Хранилище' },
  { id: 'interface', label: 'Интерфейс' },
  { id: 'diagnostics', label: 'Диагностика' },
]

const STAGE_LABELS: Record<string, string> = { search: 'Поиск', details: 'Тайтл', episodes: 'Серии', voiceovers: 'Озвучки', stream: 'Поток' }

function Section({ id, title, description, children }: { id: string; title: string; description?: string; children: ReactNode }) {
  return (
    <section id={id} className="panel scroll-mt-24 p-5 sm:p-6">
      <h2 className="text-[1.05rem] font-bold">{title}</h2>
      {description && <p className="mt-1 text-[0.86rem] leading-6 text-fog">{description}</p>}
      <div className="mt-4">{children}</div>
    </section>
  )
}

function VoiceoverPriority({ value, onChange }: { value: string[]; onChange: (next: string[]) => void }) {
  const [draft, setDraft] = useState('')
  const move = (index: number, delta: number) => {
    const next = [...value]
    const [item] = next.splice(index, 1)
    next.splice(index + delta, 0, item)
    onChange(next)
  }
  return (
    <div>
      <p className="text-[0.93rem] font-semibold">Приоритет озвучек</p>
      <p className="mt-0.5 text-[0.83rem] text-fog">Режим «Авто» выбирает первую доступную из списка, иначе — любую рабочую.</p>
      <ol className="mt-3 space-y-1.5">
        {value.map((voice, index) => (
          <li key={voice} className="flex items-center gap-2 rounded-xl border border-line bg-ink px-3 py-1.5">
            <span className="tabular w-5 text-[0.8rem] font-bold text-dim">{index + 1}</span>
            <span className="flex-1 truncate text-[0.9rem] font-semibold">{voice}</span>
            <IconButton icon="up" label={`Поднять ${voice}`} size={30} disabled={index === 0} onClick={() => move(index, -1)} />
            <IconButton icon="down" label={`Опустить ${voice}`} size={30} disabled={index === value.length - 1} onClick={() => move(index, 1)} />
            <IconButton icon="close" label={`Убрать ${voice}`} size={30} onClick={() => onChange(value.filter((v) => v !== voice))} />
          </li>
        ))}
      </ol>
      <form
        className="mt-2 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          const name = draft.trim()
          if (name && !value.some((v) => v.toLowerCase() === name.toLowerCase())) onChange([...value, name])
          setDraft('')
        }}
      >
        <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Например, AniDUB" maxLength={128} className="field h-10" aria-label="Новая озвучка" />
        <Button type="submit" icon="plus" disabled={!draft.trim()}>
          Добавить
        </Button>
      </form>
    </div>
  )
}

function ProviderRow({ provider, settings, onToggle, onDefault, onChecked }: {
  provider: ProviderInfo
  settings: AppSettings
  onToggle: (enabled: boolean) => void
  onDefault: () => void
  onChecked: (info: ProviderInfo) => void
}) {
  const toast = useToast()
  const [checking, setChecking] = useState(false)
  const enabled = settings.enabled_sources.includes(provider.id)
  const isDefault = settings.default_source === provider.id

  async function check() {
    setChecking(true)
    try {
      onChecked(await api.checkProvider(provider.id))
    } catch (err) {
      toast.show(errorMessage(err), 'error')
    } finally {
      setChecking(false)
    }
  }

  return (
    <li className="rounded-xl border border-line bg-ink p-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <StatusDot status={provider.status} />
        <span className="font-bold">{provider.label}</span>
        {provider.stable ? <Badge tone="offline">Стабильный</Badge> : <Badge tone="warn">Экспериментальный</Badge>}
        {isDefault && <Badge tone="violet">По умолчанию</Badge>}
        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="ghost" icon="pulse" loading={checking} onClick={() => void check()}>
            {checking ? 'Проверяем…' : 'Проверить'}
          </Button>
          <button
            type="button"
            role="switch"
            aria-checked={enabled}
            aria-label={`Искать в ${provider.label}`}
            onClick={() => onToggle(!enabled)}
            className={cx('relative h-6 w-11 shrink-0 rounded-full transition-colors', enabled ? 'bg-violet' : 'bg-white/[0.12]')}
          >
            <span className={cx('absolute top-0.5 size-5 rounded-full bg-white shadow transition-[left]', enabled ? 'left-[22px]' : 'left-0.5')} />
          </button>
        </div>
      </div>
      {provider.note && <p className="mt-2 text-[0.82rem] leading-5 text-fog">{provider.note}</p>}
      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {Object.entries(STAGE_LABELS).map(([stage, label]) => {
          const result = provider.stages[stage as keyof ProviderInfo['stages']]
          return (
            <span
              key={stage}
              title={result?.error || (result ? `${result.latency_ms ?? '?'} мс` : 'не проверялось')}
              className={cx(
                'inline-flex h-6 items-center gap-1 rounded-md px-2 text-[0.72rem] font-semibold',
                !result ? 'bg-white/[0.04] text-dim' : result.ok ? 'bg-offline/12 text-offline' : 'bg-danger/12 text-danger',
              )}
            >
              <Icon name={!result ? 'info' : result.ok ? 'check' : 'close'} size={12} />
              {label}
            </span>
          )
        })}
        {provider.last_check_at && <span className="ml-1 text-[0.75rem] text-dim">проверено {relativeDate(new Date(provider.last_check_at * 1000).toISOString())}</span>}
        {!isDefault && enabled && (
          <button type="button" onClick={onDefault} className="ml-auto text-[0.8rem] font-semibold text-violet-text hover:text-paper">
            Сделать основным
          </button>
        )}
      </div>
      {Object.values(provider.stages).find((r) => r && !r.ok)?.error && (
        <p className="mt-2 text-[0.8rem] text-danger">{Object.values(provider.stages).find((r) => r && !r.ok)?.error}</p>
      )}
      {provider.stages.search?.ok && provider.stages.search.error && <p className="mt-2 text-[0.8rem] text-fog">{provider.stages.search.error}</p>}
    </li>
  )
}

export function SettingsPage() {
  const toast = useToast()
  const location = useLocation()
  const settings = useResource(() => api.settings(), [])
  const providers = useResource(() => api.providers(), [])
  const stats = useResource(() => api.libraryStats(), [])
  const diagnostics = useResource(() => api.diagnostics(), [])
  const prefs = usePrefs()
  const [proxyDraft, setProxyDraft] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [rescanning, setRescanning] = useState(false)
  const [clearingHistory, setClearingHistory] = useState(false)

  useEffect(() => {
    if (location.hash && settings.data) document.getElementById(location.hash.slice(1))?.scrollIntoView({ block: 'start' })
  }, [location.hash, settings.data])

  async function update(patch: Partial<AppSettings>, message = 'Сохранено') {
    const previous = settings.data
    if (previous) settings.setData({ ...previous, ...patch })
    setSaving(true)
    try {
      const next = await api.updateSettings(patch)
      settings.setData(next)
      toast.show(message)
      if ('enabled_sources' in patch || 'default_source' in patch) providers.reload()
      return true
    } catch (err) {
      if (previous) settings.setData(previous)
      toast.show(errorMessage(err), 'error')
      return false
    } finally {
      setSaving(false)
    }
  }

  const s = settings.data
  if (settings.error) return <div className="page"><Notice title="Настройки не загрузились">{errorMessage(settings.error)}</Notice></div>
  if (!s) return <div className="page space-y-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-40 rounded-[var(--radius-card)]" />)}</div>

  const proxyValue = proxyDraft ?? s.http_proxy ?? ''
  const diag = diagnostics.data

  return (
    <div className="page">
      <h1 className="display text-[1.7rem] font-semibold sm:text-[2rem]">Настройки</h1>
      <div className="mt-7 grid gap-8 lg:grid-cols-[200px_1fr]">
        <nav aria-label="Разделы настроек" className="no-scrollbar -mx-4 flex gap-1 overflow-x-auto px-4 lg:sticky lg:top-24 lg:mx-0 lg:h-fit lg:flex-col lg:px-0">
          {SECTIONS.map((section) => (
            <a key={section.id} href={`#${section.id}`} className="shrink-0 rounded-lg px-3 py-2 text-[0.88rem] font-semibold text-fog hover:bg-white/[0.05] hover:text-paper">
              {section.label}
            </a>
          ))}
        </nav>

        <div className="max-w-3xl space-y-5" aria-busy={saving}>
          <Section id="playback" title="Воспроизведение">
            <VoiceoverPriority value={s.preferred_voiceovers} onChange={(next) => void update({ preferred_voiceovers: next }, 'Приоритет озвучек сохранён')} />
            <div className="mt-5 border-t border-line pt-4">
              <p className="mb-2 text-[0.93rem] font-semibold">Качество по умолчанию</p>
              <Segmented<number>
                label="Качество по умолчанию"
                value={s.default_quality}
                onChange={(q) => void update({ default_quality: q })}
                options={[360, 480, 720, 1080].map((q) => ({ value: q, label: `${q}p` }))}
              />
              <p className="mt-2 text-[0.82rem] text-fog">Выбирается ближайшее доступное качество не выше указанного.</p>
            </div>
            <div className="mt-2 divide-y divide-line">
              <Toggle checked={s.autoplay_next} onChange={(v) => void update({ autoplay_next: v })} label="Автоматически включать следующую серию" description="Через 5 секунд после окончания, если следующая серия существует." />
              <Toggle checked={s.remember_volume} onChange={(v) => void update({ remember_volume: v })} label="Запоминать громкость" />
            </div>
          </Section>

          <Section id="downloads" title="Загрузки">
            <p className="mb-2 text-[0.93rem] font-semibold">Одновременных загрузок</p>
            <Segmented<number>
              label="Одновременных загрузок"
              value={s.max_concurrent_downloads}
              onChange={(n) => void update({ max_concurrent_downloads: n })}
              options={[1, 2, 3, 4].map((n) => ({ value: n, label: String(n) }))}
            />
            <div className="mt-3 divide-y divide-line">
              <Toggle
                checked={s.steam_deck_optimize}
                onChange={(v) => void update({ steam_deck_optimize: v })}
                label="Сжимать для Steam Deck"
                description="После загрузки серия перекодируется в H.265 с меньшим разрешением. Это медленно, но экономит место. Если перекодирование не удастся, останется исходный файл."
              />
            </div>
            {s.steam_deck_optimize && (
              <div className="mt-3 grid gap-4 sm:grid-cols-2">
                <label className="block">
                  <span className="text-[0.88rem] font-semibold">Высота кадра</span>
                  <select className="field mt-1.5" value={s.steam_deck_height} onChange={(e) => void update({ steam_deck_height: Number(e.target.value) })}>
                    {[480, 540, 720, 800, 1080].map((h) => (
                      <option key={h} value={h}>
                        {h}p
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="text-[0.88rem] font-semibold">Качество сжатия (CRF {s.steam_deck_crf})</span>
                  <input
                    type="range"
                    min={18}
                    max={32}
                    value={s.steam_deck_crf}
                    onChange={(e) => settings.setData({ ...s, steam_deck_crf: Number(e.target.value) })}
                    onPointerUp={(e) => void update({ steam_deck_crf: Number((e.target as HTMLInputElement).value) })}
                    onKeyUp={(e) => void update({ steam_deck_crf: Number((e.target as HTMLInputElement).value) })}
                    className="mt-3 w-full accent-[var(--color-violet)]"
                  />
                  <span className="mt-1 flex justify-between text-[0.75rem] text-fog">
                    <span>лучше</span>
                    <span>меньше файл</span>
                  </span>
                </label>
              </div>
            )}
          </Section>

          <Section id="providers" title="Источники" description="Статус обновляется по реальным запросам. «Работает» показывается, только когда последние проверки всех этапов — от поиска до потока — прошли успешно.">
            {providers.error ? <Notice>{errorMessage(providers.error)}</Notice> : null}
            <ul className="space-y-2">
              {(providers.data ?? []).map((p) => (
                <ProviderRow
                  key={p.id}
                  provider={p}
                  settings={s}
                  onToggle={(enabled) => {
                    const next = enabled ? [...s.enabled_sources, p.id] : s.enabled_sources.filter((x) => x !== p.id)
                    if (!next.length) return toast.show('Нужен хотя бы один включённый источник', 'error')
                    void update({ enabled_sources: next, ...(p.id === s.default_source && !enabled ? { default_source: next[0] } : {}) })
                  }}
                  onDefault={() => void update({ default_source: p.id }, `${p.label} — основной источник`)}
                  onChecked={(info) => providers.setData((list) => (list ?? []).map((x) => (x.id === info.id ? info : x)))}
                />
              ))}
            </ul>
          </Section>

          <Section id="network" title="Сеть" description="Прокси используется для поиска, просмотра и загрузок одновременно — ссылки некоторых видеохостингов привязаны к IP-адресу.">
            <form
              className="flex flex-col gap-2 sm:flex-row"
              onSubmit={async (e) => {
                e.preventDefault()
                if (await update({ http_proxy: proxyValue.trim() || null }, proxyValue.trim() ? 'Прокси сохранён' : 'Прокси отключён')) setProxyDraft(null)
              }}
            >
              <label className="flex-1">
                <span className="sr-only">Адрес прокси</span>
                <input value={proxyValue} onChange={(e) => setProxyDraft(e.target.value)} placeholder="http://127.0.0.1:7890 или socks5://host:1080" className="field" spellCheck={false} />
              </label>
              <Button type="submit" variant="primary" disabled={proxyDraft === null}>
                Сохранить
              </Button>
            </form>
            <p className="mt-2 text-[0.82rem] text-fog">Оставьте пустым, если источники доступны напрямую.</p>
          </Section>

          <Section id="storage" title="Хранилище">
            {stats.data && (
              <dl className="tabular grid gap-3 text-[0.9rem] sm:grid-cols-3">
                <div><dt className="text-fog">Библиотека</dt><dd className="font-bold">{formatBytes(stats.data.size_bytes)}</dd></div>
                <div><dt className="text-fog">Свободно на диске</dt><dd className="font-bold">{formatBytes(stats.data.disk_free)}</dd></div>
                <div><dt className="text-fog">Серий</dt><dd className="font-bold">{stats.data.episodes}</dd></div>
                <div className="sm:col-span-3"><dt className="text-fog">Папка</dt><dd className="break-all font-mono text-[0.82rem]">{stats.data.library_path}</dd></div>
              </dl>
            )}
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                icon="retry"
                loading={rescanning}
                onClick={async () => {
                  setRescanning(true)
                  try {
                    const r = await api.rescanLibrary()
                    toast.show(`Пересканировано: добавлено ${r.imported}, убрано записей без файлов ${r.removed_missing}, пустых папок ${r.removed_empty_dirs}`, 'info')
                    stats.reload()
                  } catch (err) {
                    toast.show(errorMessage(err), 'error')
                  } finally {
                    setRescanning(false)
                  }
                }}
              >
                Пересканировать библиотеку
              </Button>
              <Button
                variant="ghost"
                loading={clearingHistory}
                onClick={async () => {
                  setClearingHistory(true)
                  try {
                    await api.clearHistory()
                    toast.show('История просмотра очищена')
                  } catch (err) {
                    toast.show(errorMessage(err), 'error')
                  } finally {
                    setClearingHistory(false)
                  }
                }}
              >
                Очистить историю просмотра
              </Button>
            </div>
            <p className="mt-2 text-[0.82rem] text-fog">Пересканирование убирает записи о файлах, удалённых вручную, и находит серии, скачанные AnimeBox ранее. Файлы не удаляются.</p>
          </Section>

          <Section id="interface" title="Интерфейс" description="Эти настройки хранятся только в этом браузере.">
            <div className="divide-y divide-line">
              <Toggle checked={prefs.reduceMotion} onChange={(v) => setPrefs({ reduceMotion: v })} label="Меньше анимации" description="Отключает переходы и анимацию загрузки — полезно на слабом железе." />
              <Toggle checked={prefs.compactGrid} onChange={(v) => setPrefs({ compactGrid: v })} label="Компактная сетка постеров" description="Больше постеров на экране, например на Steam Deck." />
            </div>
          </Section>

          <Section id="diagnostics" title="Диагностика">
            {diagnostics.error ? <Notice>{errorMessage(diagnostics.error)}</Notice> : null}
            {diag && (
              <>
                <dl className="grid gap-x-6 gap-y-2.5 text-[0.86rem] sm:grid-cols-[160px_1fr]">
                  <dt className="text-fog">Версия</dt>
                  <dd className="font-semibold">AnimeBox {diag.version} · Python {diag.python}{diag.frozen ? ' · portable' : ''}</dd>
                  <dt className="text-fog">Система</dt>
                  <dd>{diag.platform}</dd>
                  <dt className="text-fog">FFmpeg</dt>
                  <dd className={diag.ffmpeg.path ? '' : 'text-danger'}>
                    {diag.ffmpeg.path ? (
                      <>
                        <span className="block">{diag.ffmpeg.version || 'найден'}</span>
                        <span className="break-all font-mono text-[0.78rem] text-fog">{diag.ffmpeg.path}</span>
                      </>
                    ) : (
                      'Не найден — HLS-загрузки недоступны. Офлайн-просмотр работает.'
                    )}
                  </dd>
                  <dt className="text-fog">Данные</dt>
                  <dd className="break-all font-mono text-[0.78rem]">{diag.paths.database}</dd>
                  <dt className="text-fog">Прокси</dt>
                  <dd>{diag.network.proxy || 'не используется'}</dd>
                  <dt className="text-fog">Сейчас</dt>
                  <dd>загрузок: {diag.runtime.running_downloads} из {diag.runtime.max_concurrent_downloads} · медиасессий: {diag.runtime.media_sessions}</dd>
                </dl>
                <div className="mt-4 flex gap-2">
                  <Button
                    size="sm"
                    icon="copy"
                    onClick={() => {
                      void navigator.clipboard
                        ?.writeText(JSON.stringify(diag, null, 2))
                        .then(() => toast.show('Диагностика скопирована'))
                        .catch(() => toast.show('Буфер обмена недоступен', 'error'))
                    }}
                  >
                    Скопировать для отчёта об ошибке
                  </Button>
                  <Button size="sm" variant="ghost" icon="retry" onClick={diagnostics.reload}>
                    Обновить
                  </Button>
                </div>
              </>
            )}
          </Section>
        </div>
      </div>
    </div>
  )
}
