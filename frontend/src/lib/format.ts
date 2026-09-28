import type { FindingSeverity, GapType, RiskBand } from './types'

export const pct = (x: number | null | undefined, digits = 0): string =>
  x === null || x === undefined ? '-' : `${(x * 100).toFixed(digits)}%`

export const num = (x: number | null | undefined): string =>
  x === null || x === undefined ? '-' : x.toLocaleString()

export const title = (s: string): string =>
  s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

export const shortDate = (s: string | null | undefined): string =>
  !s ? '-' : s.replace('T', ' ').slice(0, 16)

export const bandClass = (band: RiskBand | string): string => {
  switch (band) {
    case 'High':
      return 'bg-risk-highbg text-risk-high border-risk-high/30'
    case 'Medium':
      return 'bg-risk-mediumbg text-risk-medium border-risk-medium/30'
    default:
      return 'bg-risk-lowbg text-risk-low border-risk-low/30'
  }
}

export const severityClass = (severity: FindingSeverity | string): string => {
  switch (severity) {
    case 'high':
      return 'bg-risk-highbg text-risk-high border-risk-high/30'
    case 'medium':
      return 'bg-risk-mediumbg text-risk-medium border-risk-medium/30'
    default:
      return 'bg-ink-100 text-ink-700 border-ink-300'
  }
}

export const gapLabel: Record<GapType, string> = {
  execution_gap: 'Execution gap',
  negative_space: 'Negative space',
  anomaly: 'Anomaly',
  data_quality: 'Data quality',
}

export const gapClass: Record<GapType, string> = {
  execution_gap: 'bg-accent-50 text-accent-700 border-accent-300',
  negative_space: 'bg-purple-50 text-purple-700 border-purple-200',
  anomaly: 'bg-amber-50 text-amber-700 border-amber-200',
  data_quality: 'bg-slate-100 text-slate-700 border-slate-300',
}

export const statusLabel: Record<string, string> = {
  open: 'Open',
  valid: 'Confirmed valid',
  not_valid: 'Dismissed',
}

/** 0-100 capability score -> heatmap colour. Green = nothing flagged. */
export const scoreColour = (score: number): string => {
  if (score >= 90) return '#dcfce7'
  if (score >= 75) return '#fef9c3'
  if (score >= 55) return '#fed7aa'
  if (score >= 35) return '#fecaca'
  return '#fca5a5'
}

export const scoreTextColour = (score: number): string =>
  score >= 75 ? '#14532d' : score >= 35 ? '#7c2d12' : '#7f1d1d'

export const trendArrow = (direction: string): { glyph: string; cls: string; label: string } => {
  if (direction === 'worsening')
    return { glyph: '▲', cls: 'text-risk-high', label: 'Worsening vs previous 30 days' }
  if (direction === 'improving')
    return { glyph: '▼', cls: 'text-risk-low', label: 'Improving vs previous 30 days' }
  return { glyph: '▬', cls: 'text-ink-500', label: 'Broadly unchanged' }
}

export const metricLabel = (key: string): string =>
  key
    .replace(/_/g, ' ')
    .replace(/\b(sla|id|ids|pp)\b/gi, (m) => m.toUpperCase())
    .replace(/^\w/, (c) => c.toUpperCase())

export const formatMetricValue = (value: unknown): string => {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'number') {
    if (Number.isInteger(value)) return value.toLocaleString()
    return Math.abs(value) < 1 ? value.toFixed(4) : value.toFixed(2)
  }
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  return String(value)
}
