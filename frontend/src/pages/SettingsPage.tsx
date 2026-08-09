import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { AppSettings } from '../api/types'

export function SettingsPage() {
  const [form, setForm] = useState<AppSettings | null>(null)
  const [voiceText, setVoiceText] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  useEffect(() => { api.settings().then((s) => { setForm(s); setVoiceText(s.preferred_voiceovers.join(', ')) }).catch((err) => setError(err instanceof Error ? err.message : 'Настройки недоступны')) }, [])

  async function onSave(e: React.FormEvent) {
    e.preventDefault(); if (!form) return; setSaving(true); setMessage(null); setError(null)
    try {
      const preferred = voiceText.split(',').map((v) => v.trim()).filter(Boolean)
      const updated = await api.updateSettings({ ...form, preferred_voiceovers: preferred, http_proxy: form.http_proxy || null })
      setForm(updated); setVoiceText(updated.preferred_voiceovers.join(', ')); setMessage('Настройки сохранены')
    } catch (err) { setError(err instanceof Error ? err.message : 'Не удалось сохранить') } finally { setSaving(false) }
  }

  if (!form) return <p className="text-fog">{error || 'Загружаем настройки…'}</p>
  const inputClass = 'field w-full'

  return (
    <div className="animate-rise mx-auto max-w-4xl space-y-8">
      <header className="border-b border-white/8 pb-7"><p className="eyebrow">Поведение AnimeBox</p><h1 className="mt-2 font-display text-4xl font-extrabold tracking-[-0.04em] sm:text-5xl">Настройки</h1><p className="mt-3 text-fog">Озвучки, качество, сеть и подготовка файлов для Steam Deck.</p></header>
      <form onSubmit={onSave} className="space-y-5">
        <section className="surface space-y-5 rounded-3xl p-5 sm:p-7">
          <div><p className="eyebrow">Воспроизведение</p><h2 className="mt-1 font-display text-xl font-bold">Предпочтения</h2></div>
          <label className="block space-y-2"><span className="text-sm font-bold">Любимые озвучки</span><input value={voiceText} onChange={(e) => setVoiceText(e.target.value)} className={inputClass} placeholder="AniLibria, AnimeVost" /><span className="block text-xs leading-5 text-fog">Через запятую, в порядке приоритета. Первая доступная включится автоматически.</span></label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block space-y-2"><span className="text-sm font-bold">Качество</span><select value={form.default_quality} onChange={(e) => setForm({ ...form, default_quality: Number(e.target.value) })} className={inputClass}>{[360,480,720,1080].map((q) => <option key={q} value={q}>{q}p</option>)}</select></label>
            <label className="block space-y-2"><span className="text-sm font-bold">Источник по умолчанию</span><input value={form.default_source} onChange={(e) => setForm({ ...form, default_source: e.target.value })} className={inputClass} /></label>
          </div>
        </section>

        <section className="surface space-y-5 rounded-3xl p-5 sm:p-7">
          <div><p className="eyebrow">Устройство и сеть</p><h2 className="mt-1 font-display text-xl font-bold">Загрузки</h2></div>
          <label className="block space-y-2"><span className="text-sm font-bold">HTTP-прокси</span><input value={form.http_proxy || ''} onChange={(e) => setForm({ ...form, http_proxy: e.target.value })} className={inputClass} placeholder="http://127.0.0.1:7890" /><span className="block text-xs text-fog">Оставьте пустым, если источники доступны напрямую.</span></label>
          <label className="flex items-start gap-3 rounded-2xl border border-white/8 bg-black/15 p-4"><input type="checkbox" checked={form.steam_deck_optimize} onChange={(e) => setForm({ ...form, steam_deck_optimize: e.target.checked })} className="mt-0.5 size-4 accent-amber" /><span><span className="block text-sm font-bold">Оптимизировать для Steam Deck</span><span className="mt-1 block text-xs leading-5 text-fog">Перекодировать в H.265 и снизить разрешение, чтобы экономить место.</span></span></label>
          <div className="grid grid-cols-2 gap-4"><label className="block space-y-2"><span className="text-sm font-bold">CRF</span><input type="number" value={form.steam_deck_crf} onChange={(e) => setForm({ ...form, steam_deck_crf: Number(e.target.value) })} className={inputClass} /></label><label className="block space-y-2"><span className="text-sm font-bold">Высота, px</span><input type="number" value={form.steam_deck_height} onChange={(e) => setForm({ ...form, steam_deck_height: Number(e.target.value) })} className={inputClass} /></label></div>
        </section>

        <div className="flex flex-wrap items-center gap-4"><button type="submit" disabled={saving} className="btn-primary">{saving ? 'Сохраняем…' : 'Сохранить изменения'}</button>{message && <p className="text-sm font-bold text-ok">✓ {message}</p>}{error && <p className="text-sm text-danger">{error}</p>}</div>
      </form>
    </div>
  )
}
