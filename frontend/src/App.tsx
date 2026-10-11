import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { ToastProvider } from './components/toast'
import { ButtonLink, EmptyState, Spinner } from './components/ui'
import { AnimePage } from './pages/AnimePage'
import { DownloadsPage } from './pages/DownloadsPage'
import { HomePage } from './pages/HomePage'
import { LibraryPage } from './pages/LibraryPage'
import { SearchPage } from './pages/SearchPage'
import { SettingsPage } from './pages/SettingsPage'

// hls.js is only needed for playback; keep it out of the initial bundle.
const PlayerPage = lazy(() => import('./pages/PlayerPage').then((m) => ({ default: m.PlayerPage })))

function NotFound() {
  return (
    <div className="page">
      <EmptyState icon="info" title="Страница не найдена" action={<ButtonLink to="/" variant="primary">На главную</ButtonLink>}>
        Такой страницы в AnimeBox нет.
      </EmptyState>
    </div>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route
            path="player/:id"
            element={
              <Suspense fallback={<div className="grid min-h-screen place-items-center bg-black"><Spinner size={36} className="text-violet-hi" /></div>}>
                <PlayerPage />
              </Suspense>
            }
          />
          <Route element={<AppShell />}>
            <Route index element={<HomePage />} />
            <Route path="search" element={<SearchPage />} />
            <Route path="library" element={<LibraryPage />} />
            <Route path="anime/:id" element={<AnimePage />} />
            <Route path="downloads" element={<DownloadsPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  )
}
