import { useCallback, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'

import { api } from '../lib/api'
import { shortDate } from '../lib/format'
import { useApi } from '../lib/useApi'
import type { Run } from '../lib/types'

const NAV = [
  { to: '/', label: 'Overview', icon: '▦', end: true },
  { to: '/entities', label: 'Organisations', icon: '▤' },
  { to: '/negative-space', label: 'Negative Space', icon: '◍' },
  { to: '/upload', label: 'Upload', icon: '⇪' },
  { to: '/validation', label: 'Validation', icon: '✓' },
  { to: '/methodology', label: 'Methodology', icon: 'ℹ' },
  { to: '/audit', label: 'Audit Log', icon: '⧉' },
]

export default function Layout() {
  const navigate = useNavigate()
  const run = useApi<Run>(() => api.latestRun().catch(() => null as unknown as Run), [])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const runAnalysis = useCallback(async () => {
    setBusy(true)
    setMessage(null)
    try {
      const result = await api.runAnalysis()
      setMessage(`Run ${result.run_id} complete - ${result.finding_count} findings`)
      run.reload()
      // Force every page to refetch against the new run.
      navigate(0)
    } catch (err) {
      setMessage((err as Error).message)
    } finally {
      setBusy(false)
    }
  }, [navigate, run])

  return (
    <div className="flex min-h-full">
      <aside className="flex w-64 shrink-0 flex-col bg-navy-900 text-white">
        <div className="border-b border-white/10 px-5 py-5">
          <p className="text-lg font-bold leading-tight">SAT-SA Lens</p>
          <p className="mt-1 text-[11px] leading-snug text-white/60">
            Supervisory analytics for SOC assessment
          </p>
          <p className="mt-2 text-[10px] font-semibold uppercase tracking-wider text-white/40">
            NCIIPC &middot; SIH26157
          </p>
        </div>
        <nav className="flex-1 space-y-0.5 p-3">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? 'bg-accent-500 font-semibold text-white'
                    : 'text-white/75 hover:bg-white/10 hover:text-white'
                }`
              }
            >
              <span aria-hidden className="w-4 text-center opacity-80">
                {item.icon}
              </span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-white/10 px-5 py-4 text-[11px] leading-relaxed text-white/50">
          <p className="font-semibold text-white/70">Offline deployment</p>
          <p className="mt-1">
            No external network calls. All models, fonts and data are held locally.
          </p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-ink-100 bg-white px-6 py-3">
          <div className="min-w-0">
            <p className="label">Latest analysis run</p>
            {run.data ? (
              <p className="mono truncate text-ink-700">
                {run.data.run_id}
                <span className="mx-2 text-ink-300">|</span>
                {shortDate(run.data.started_at)}
                <span className="mx-2 text-ink-300">|</span>
                rules v{run.data.rules_version}
                <span className="mx-2 text-ink-300">|</span>
                data {String(run.data.data_hash).slice(0, 12)}
              </p>
            ) : (
              <p className="text-sm text-ink-500">No run yet - press Run analysis</p>
            )}
          </div>
          <div className="flex items-center gap-3">
            {message && <span className="text-xs text-ink-500">{message}</span>}
            <button className="btn-primary" onClick={runAnalysis} disabled={busy}>
              {busy ? 'Running analysis...' : 'Run analysis'}
            </button>
          </div>
        </header>
        <main className="min-w-0 flex-1 p-6">
          <Outlet />
        </main>
        <footer className="border-t border-ink-100 bg-white px-6 py-3 text-[11px] text-ink-500">
          Every finding is a hypothesis for a human supervisor to confirm. SAT-SA Lens never
          concludes that an organisation has failed.
        </footer>
      </div>
    </div>
  )
}
