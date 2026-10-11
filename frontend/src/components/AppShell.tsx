import { useEffect, useRef, useState, type FormEvent } from 'react'
import { NavLink, Outlet, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import { routes } from '../lib/routes'
import { useInterval } from '../lib/useResource'
import { Icon, type IconName } from './icons'
import { useToast } from './toast'
import { ConfirmDialog } from './ui'
import { cx } from '../lib/cx'

const NAV: { to: string; label: string; icon: IconName; end?: boolean }[] = [
  { to: '/', label: 'Главная', icon: 'home', end: true },
  { to: '/search', label: 'Поиск', icon: 'search' },
  { to: '/library', label: 'Библиотека', icon: 'library' },
  { to: '/downloads', label: 'Загрузки', icon: 'download' },
  { to: '/settings', label: 'Настройки', icon: 'settings' },
]

function Logo({ compact }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <span className="relative grid size-9 shrink-0 place-items-center rounded-[11px] bg-violet shadow-[0_0_24px_-4px_rgba(139,108,255,0.8)]">
        <span className="display text-[1.05rem] font-bold leading-none text-white">A</span>
        <span className="absolute bottom-[7px] right-[7px] size-1.5 rounded-full bg-offline" />
      </span>
      {!compact && (
        <span className="display text-[1.05rem] font-semibold tracking-[-0.03em]">
          Anime<span className="text-violet-text">Box</span>
        </span>
      )}
    </span>
  )
}

function useActiveDownloads(): number {
  const [count, setCount] = useState(0)
  const refresh = () =>
    api
      .downloads('active')
      .then((jobs) => setCount(jobs.filter((j) => j.status !== 'paused').length))
      .catch(() => {})
  useEffect(() => {
    void refresh()
  }, [])
  useInterval(refresh, 5000)
  return count
}

function GlobalSearch() {
  const navigate = useNavigate()
  const location = useLocation()
  const [params] = useSearchParams()
  const [value, setValue] = useState('')
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (location.pathname === '/search') setValue(params.get('q') || '')
  }, [location.pathname, params])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      const typing = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)
      if ((event.key === '/' && !typing) || (event.key.toLowerCase() === 'k' && (event.ctrlKey || event.metaKey))) {
        event.preventDefault()
        input.current?.focus()
        input.current?.select()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  function submit(event: FormEvent) {
    event.preventDefault()
    const query = value.trim()
    if (!query) return
    navigate(routes.search(query, params.get('source') || undefined))
    input.current?.blur()
  }

  return (
    <form onSubmit={submit} role="search" className="relative w-full max-w-xl">
      <Icon name="search" size={18} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-dim" />
      <input
        ref={input}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Найти аниме"
        aria-label="Найти аниме"
        maxLength={200}
        className="h-10 w-full rounded-xl border border-line bg-white/[0.04] pl-10 pr-12 text-[0.92rem] outline-none transition placeholder:text-dim hover:bg-white/[0.06] focus:border-violet/60 focus:bg-ink"
      />
      <kbd className="pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 rounded-md border border-line px-1.5 text-[0.7rem] font-semibold text-dim sm:block">/</kbd>
    </form>
  )
}

export function AppShell() {
  const activeDownloads = useActiveDownloads()
  const toast = useToast()
  const [canStop, setCanStop] = useState(false)
  const [confirmStop, setConfirmStop] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [stopped, setStopped] = useState(false)
  const location = useLocation()

  useEffect(() => {
    api.session().then((s) => setCanStop(s.shutdown_enabled)).catch(() => {})
  }, [])

  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [location.pathname])

  async function stop() {
    setStopping(true)
    try {
      await api.shutdown()
      setStopped(true)
    } catch (err) {
      toast.show(errorMessage(err, 'Не удалось остановить AnimeBox'), 'error')
    } finally {
      setStopping(false)
      setConfirmStop(false)
    }
  }

  if (stopped) {
    return (
      <div className="grid min-h-screen place-items-center px-6 text-center">
        <div>
          <Logo />
          <h1 className="display mt-8 text-2xl font-semibold">AnimeBox остановлен</h1>
          <p className="mt-2 text-fog">Вкладку можно закрыть. Незавершённые загрузки снова встанут в очередь при следующем запуске.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen lg:pl-[76px] xl:pl-[232px]">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[90] focus:rounded-lg focus:bg-violet focus:px-3 focus:py-2">
        Перейти к содержимому
      </a>

      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[76px] flex-col border-r border-line bg-ink/95 px-3 py-5 lg:flex xl:w-[232px] xl:px-4">
        <NavLink to="/" className="mb-8 px-1.5" aria-label="AnimeBox — главная">
          <span className="xl:hidden">
            <Logo compact />
          </span>
          <span className="hidden xl:inline">
            <Logo />
          </span>
        </NavLink>
        <nav className="flex flex-1 flex-col gap-1" aria-label="Основная навигация">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              title={item.label}
              className={({ isActive }) =>
                cx(
                  'group relative flex h-11 items-center gap-3 rounded-xl px-3 text-[0.92rem] font-semibold transition-colors',
                  isActive ? 'bg-violet/14 text-paper' : 'text-fog hover:bg-white/[0.05] hover:text-paper',
                )
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && <span className="absolute -left-3 top-2.5 h-6 w-[3px] rounded-r-full bg-violet xl:-left-4" />}
                  <Icon name={item.icon} size={20} className={isActive ? 'text-violet-text' : ''} />
                  <span className="hidden xl:inline">{item.label}</span>
                  {item.to === '/downloads' && activeDownloads > 0 && (
                    <span className="tabular absolute right-1.5 top-1.5 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-violet px-1 text-[0.68rem] font-bold text-white xl:static xl:ml-auto">
                      {activeDownloads}
                    </span>
                  )}
                </>
              )}
            </NavLink>
          ))}
        </nav>
        {canStop && (
          <button
            type="button"
            onClick={() => setConfirmStop(true)}
            title="Остановить AnimeBox"
            className="flex h-11 items-center gap-3 rounded-xl px-3 text-[0.88rem] font-semibold text-fog transition-colors hover:bg-danger/10 hover:text-danger"
          >
            <Icon name="power" size={20} />
            <span className="hidden xl:inline">Остановить</span>
          </button>
        )}
      </aside>

      <header className="glass sticky top-0 z-30 border-b border-line">
        <div className="mx-auto flex h-16 max-w-[1480px] items-center gap-3 px-4 sm:px-6 lg:px-10">
          <NavLink to="/" className="lg:hidden" aria-label="AnimeBox — главная">
            <Logo compact />
          </NavLink>
          <GlobalSearch />
          {canStop && (
            <button
              type="button"
              onClick={() => setConfirmStop(true)}
              aria-label="Остановить AnimeBox"
              className="grid size-10 shrink-0 place-items-center rounded-xl text-fog hover:bg-danger/10 hover:text-danger lg:hidden"
            >
              <Icon name="power" size={19} />
            </button>
          )}
        </div>
      </header>

      <main id="main">
        <Outlet />
      </main>

      <nav
        aria-label="Основная навигация"
        className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t border-line bg-ink/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md lg:hidden"
      >
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cx('relative flex h-16 flex-col items-center justify-center gap-1 text-[0.68rem] font-semibold', isActive ? 'text-violet-text' : 'text-fog')
            }
          >
            <Icon name={item.icon} size={21} />
            {item.label}
            {item.to === '/downloads' && activeDownloads > 0 && (
              <span className="tabular absolute right-[calc(50%-20px)] top-2 grid h-4 min-w-4 place-items-center rounded-full bg-violet px-1 text-[0.62rem] font-bold text-white">
                {activeDownloads}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <ConfirmDialog
        open={confirmStop}
        title="Остановить AnimeBox?"
        confirmLabel="Остановить"
        busy={stopping}
        onConfirm={() => void stop()}
        onCancel={() => setConfirmStop(false)}
      >
        Локальный сервер завершит работу и освободит порт. {activeDownloads > 0 && `Активные загрузки (${activeDownloads}) снова встанут в очередь при следующем запуске; HLS-серии начнутся заново.`}
      </ConfirmDialog>
    </div>
  )
}
