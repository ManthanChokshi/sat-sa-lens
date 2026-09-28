import type { ReactNode } from 'react'

import { bandClass, gapClass, gapLabel, severityClass } from '../lib/format'
import type { FindingSeverity, GapType, RiskBand } from '../lib/types'

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-10 text-sm text-ink-500" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-ink-300 border-t-accent-500" />
      {label}...
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="card card-pad border-risk-high/30 bg-risk-highbg">
      <p className="text-sm font-semibold text-risk-high">Something went wrong</p>
      <p className="mt-1 text-sm text-ink-700">{message}</p>
      {onRetry && (
        <button className="btn-ghost mt-3" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string
  body: string
  action?: ReactNode
}) {
  return (
    <div className="card card-pad text-center">
      <p className="text-sm font-semibold text-ink-900">{title}</p>
      <p className="mx-auto mt-1 max-w-xl text-sm text-ink-500">{body}</p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  )
}

export function BandChip({ band, score }: { band: RiskBand | string; score?: number }) {
  return (
    <span className={`chip ${bandClass(band)}`}>
      {score !== undefined && <strong className="tabular-nums">{score.toFixed(0)}</strong>}
      {band}
    </span>
  )
}

export function SeverityChip({ severity }: { severity: FindingSeverity | string }) {
  return <span className={`chip ${severityClass(severity)}`}>{severity}</span>
}

export function GapChip({ gap }: { gap: GapType }) {
  return <span className={`chip ${gapClass[gap]}`}>{gapLabel[gap]}</span>
}

export function StatusChip({ status }: { status: string }) {
  const cls =
    status === 'valid'
      ? 'bg-risk-highbg text-risk-high border-risk-high/30'
      : status === 'not_valid'
        ? 'bg-ink-100 text-ink-500 border-ink-300 line-through'
        : 'bg-accent-50 text-accent-700 border-accent-300'
  const label = status === 'valid' ? 'Confirmed' : status === 'not_valid' ? 'Dismissed' : 'Open'
  return <span className={`chip ${cls}`}>{label}</span>
}

export function ConfidenceBar({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-ink-100">
        <div
          className="h-full rounded-full bg-accent-500"
          style={{ width: `${Math.max(4, value * 100)}%` }}
        />
      </div>
      <span className="tabular-nums text-xs text-ink-500">{(value * 100).toFixed(0)}%</span>
    </div>
  )
}

export function StatTile({
  label,
  value,
  hint,
  tone = 'default',
}: {
  label: string
  value: ReactNode
  hint?: string
  tone?: 'default' | 'high' | 'medium' | 'low' | 'accent'
}) {
  const tones: Record<string, string> = {
    default: 'text-ink-900',
    high: 'text-risk-high',
    medium: 'text-risk-medium',
    low: 'text-risk-low',
    accent: 'text-accent-600',
  }
  return (
    <div className="card card-pad">
      <p className="label">{label}</p>
      <p className={`mt-1 text-3xl font-semibold tabular-nums ${tones[tone]}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-ink-500">{hint}</p>}
    </div>
  )
}

export function SectionTitle({
  title,
  subtitle,
  right,
}: {
  title: string
  subtitle?: string
  right?: ReactNode
}) {
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 className="text-base font-semibold text-ink-900">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-ink-500">{subtitle}</p>}
      </div>
      {right}
    </div>
  )
}

export function Callout({
  tone = 'info',
  title,
  children,
}: {
  tone?: 'info' | 'warn' | 'ok'
  title: string
  children: ReactNode
}) {
  const tones = {
    info: 'border-accent-300 bg-accent-50',
    warn: 'border-risk-medium/30 bg-risk-mediumbg',
    ok: 'border-risk-low/30 bg-risk-lowbg',
  }
  return (
    <div className={`rounded-lg border p-4 ${tones[tone]}`}>
      <p className="text-sm font-semibold text-ink-900">{title}</p>
      <div className="mt-1 text-sm leading-relaxed text-ink-700">{children}</div>
    </div>
  )
}
