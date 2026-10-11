import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import { Icon } from './icons'
import { cx } from '../lib/cx'

type ToastTone = 'success' | 'error' | 'info'
type Toast = { id: number; tone: ToastTone; text: string; action?: { label: string; onClick: () => void } }
type ToastApi = { show: (text: string, tone?: ToastTone, action?: Toast['action']) => void }

const ToastContext = createContext<ToastApi>({ show: () => {} })

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const counter = useRef(0)

  const dismiss = useCallback((id: number) => setToasts((list) => list.filter((t) => t.id !== id)), [])
  const show = useCallback(
    (text: string, tone: ToastTone = 'success', action?: Toast['action']) => {
      const id = ++counter.current
      setToasts((list) => [...list.slice(-3), { id, tone, text, action }])
      window.setTimeout(() => dismiss(id), tone === 'error' ? 7000 : 4000)
    },
    [dismiss],
  )
  const value = useMemo(() => ({ show }), [show])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-20 z-[80] flex flex-col items-center gap-2 px-4 lg:bottom-6 lg:items-end lg:px-6">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className="glass enter pointer-events-auto flex max-w-md items-center gap-3 rounded-xl border border-line px-4 py-3 text-[0.9rem] shadow-[var(--shadow-lift)]"
          >
            <Icon
              name={toast.tone === 'error' ? 'alert' : toast.tone === 'info' ? 'info' : 'check'}
              size={18}
              className={cx('shrink-0', toast.tone === 'error' ? 'text-danger' : toast.tone === 'info' ? 'text-violet-text' : 'text-offline')}
            />
            <span className="min-w-0 flex-1">{toast.text}</span>
            {toast.action && (
              <button
                type="button"
                className="shrink-0 font-bold text-violet-text hover:text-paper"
                onClick={() => {
                  toast.action?.onClick()
                  dismiss(toast.id)
                }}
              >
                {toast.action.label}
              </button>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components -- hook belongs with its provider
export function useToast(): ToastApi {
  return useContext(ToastContext)
}
