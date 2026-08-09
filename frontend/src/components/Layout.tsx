import { NavLink, Outlet } from 'react-router-dom'

const links = [
  { to: '/search', label: 'Поиск', short: 'Поиск' },
  { to: '/library', label: 'Моя библиотека', short: 'Библиотека' },
  { to: '/downloads', label: 'Загрузки', short: 'Загрузки' },
  { to: '/settings', label: 'Настройки', short: 'Настройки' },
]

export function Layout() {
  return (
    <div className="grain relative min-h-screen">
      <header className="sticky top-0 z-50 border-b border-white/6 bg-ink/82 backdrop-blur-2xl">
        <div className="mx-auto flex h-16 max-w-[1500px] items-center gap-5 px-4 sm:px-7 lg:px-10">
          <NavLink to="/search" className="group flex shrink-0 items-center gap-2.5" aria-label="AnimeBox">
            <span className="relative grid size-8 place-items-center overflow-hidden rounded-[10px] bg-amber shadow-[0_0_28px_rgba(139,92,246,0.35)]">
              <span className="font-display text-lg font-extrabold text-white">A</span>
              <span className="absolute inset-x-0 bottom-0 h-1 bg-violet-soft" />
            </span>
            <span className="font-display text-xl font-extrabold tracking-[-0.05em] text-paper sm:text-2xl">
              Anime<span className="text-violet-soft">Box</span>
            </span>
          </NavLink>

          <nav className="ml-auto hidden items-center gap-1 md:flex">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) =>
                  [
                    'relative rounded-lg px-3.5 py-2 text-sm font-semibold transition',
                    isActive ? 'bg-white/7 text-white' : 'text-fog hover:bg-white/5 hover:text-paper',
                  ].join(' ')
                }
              >
                {({ isActive }) => (
                  <>
                    {link.label}
                    {isActive && <span className="absolute inset-x-3 -bottom-[13px] h-0.5 rounded-full bg-amber" />}
                  </>
                )}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2 md:ml-0">
            <span className="hidden rounded-full border border-ok/20 bg-ok/8 px-2.5 py-1 text-[0.65rem] font-bold uppercase tracking-[0.14em] text-ok sm:inline">
              Local
            </span>
          </div>
        </div>

        <nav className="flex overflow-x-auto border-t border-white/5 px-2 md:hidden" aria-label="Основная навигация">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                [
                  'relative min-w-max flex-1 px-3 py-2.5 text-center text-xs font-bold transition',
                  isActive ? 'text-violet-soft' : 'text-fog',
                ].join(' ')
              }
            >
              {({ isActive }) => (
                <>
                  {link.short}
                  {isActive && <span className="absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-amber" />}
                </>
              )}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="page-shell">
        <Outlet />
      </main>
    </div>
  )
}
