import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../lib/api'
import {
  num,
  scoreColour,
  scoreTextColour,
  title as titleCase,
  trendArrow,
} from '../lib/format'
import { useApi } from '../lib/useApi'
import type { Overview as OverviewData } from '../lib/types'
import {
  BandChip,
  Callout,
  EmptyState,
  ErrorState,
  SectionTitle,
  Spinner,
  StatTile,
} from '../components/ui'

export default function Overview() {
  const { data, loading, error, reload } = useApi<OverviewData>(() => api.overview(), [])
  const [sector, setSector] = useState('all')
  const [ingesting, setIngesting] = useState(false)

  const rows = useMemo(() => {
    if (!data) return []
    return sector === 'all' ? data.entities : data.entities.filter((e) => e.sector === sector)
  }, [data, sector])

  if (loading) return <Spinner label="Loading portfolio" />
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data) return null

  if (!data.entities.length) {
    return (
      <EmptyState
        title="No submissions loaded yet"
        body="Load the bundled sample corpus to see the tool working, or go to Upload to bring in a real submission."
        action={
          <button
            className="btn-primary"
            disabled={ingesting}
            onClick={async () => {
              setIngesting(true)
              try {
                await api.ingestSample()
                await api.runAnalysis()
                reload()
              } finally {
                setIngesting(false)
              }
            }}
          >
            {ingesting ? 'Loading sample data...' : 'Load sample data and analyse'}
          </button>
        }
      />
    )
  }

  const k = data.kpis
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-ink-900">Portfolio overview</h1>
        <p className="mt-1 text-sm text-ink-500">
          {num(k.entities_assessed)} critical-sector organisations assessed against their own
          submissions and their peer group.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <StatTile label="Organisations assessed" value={num(k.entities_assessed)} />
        <StatTile
          label="High risk"
          value={num(k.high_risk_entities)}
          tone="high"
          hint={`${num(k.medium_risk_entities)} medium risk`}
        />
        <StatTile
          label="Open findings"
          value={num(k.open_findings)}
          tone="accent"
          hint={`${num(k.validated_findings)} confirmed, ${num(k.dismissed_findings)} dismissed`}
        />
        <StatTile
          label="Execution gaps"
          value={num(k.execution_gaps)}
          hint="Claim looks fine, evidence does not"
        />
        <StatTile
          label="Negative space"
          value={num(k.negative_space)}
          hint={`${num(k.anomalies)} anomalies, ${num(k.data_quality)} data-quality`}
        />
      </div>

      <section className="card">
        <div className="flex flex-wrap items-end justify-between gap-3 border-b border-ink-100 px-5 py-4">
          <SectionTitle
            title="Organisations ranked by risk"
            subtitle="Risk score is the weighted sum of open and confirmed findings (severity x confidence), normalised to 0-100."
          />
          <select
            className="rounded-md border border-ink-300 px-2 py-1.5 text-sm"
            value={sector}
            onChange={(e) => setSector(e.target.value)}
          >
            <option value="all">All sectors</option>
            {data.sectors.map((s) => (
              <option key={s} value={s}>
                {titleCase(s)}
              </option>
            ))}
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px]">
            <thead>
              <tr>
                <th className="th">Organisation</th>
                <th className="th">Sector</th>
                <th className="th">Tier</th>
                <th className="th">Risk</th>
                <th className="th">Trend</th>
                <th className="th">Findings</th>
                <th className="th">Execution</th>
                <th className="th">Negative</th>
                <th className="th">Other</th>
                <th className="th">Volume</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => {
                const arrow = trendArrow(e.trend_direction)
                const gaps = e.counts_by_gap_type || {}
                return (
                  <tr key={e.entity_id} className="hover:bg-ink-50/60">
                    <td className="td">
                      <Link className="link font-medium" to={`/entities/${e.entity_id}`}>
                        {e.name}
                      </Link>
                      <div className="mono text-ink-500">{e.entity_id}</div>
                    </td>
                    <td className="td">{titleCase(e.sector)}</td>
                    <td className="td">{titleCase(e.size_tier)}</td>
                    <td className="td">
                      <BandChip band={e.risk_band} score={e.risk_score} />
                    </td>
                    <td className="td">
                      <span className={arrow.cls} title={arrow.label}>
                        {arrow.glyph}
                      </span>
                    </td>
                    <td className="td tabular-nums">
                      {e.finding_count}
                      {e.dismissed_findings > 0 && (
                        <span className="ml-1 text-xs text-ink-500">
                          (+{e.dismissed_findings} dismissed)
                        </span>
                      )}
                    </td>
                    <td className="td tabular-nums">{gaps.execution_gap || 0}</td>
                    <td className="td tabular-nums">{gaps.negative_space || 0}</td>
                    <td className="td tabular-nums">
                      {(gaps.anomaly || 0) + (gaps.data_quality || 0)}
                    </td>
                    <td className="td tabular-nums text-ink-500">
                      {num(e.alerts)} alerts / {num(e.assets)} assets
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card card-pad">
        <SectionTitle
          title="Capability heatmap"
          subtitle="0-100 per capability area. 100 means nothing was flagged there; darker red means more, or more confident, findings."
        />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[960px] border-separate border-spacing-0.5">
            <thead>
              <tr>
                <th className="th sticky left-0 z-10 bg-ink-50">Organisation</th>
                {data.capability_areas.map((area) => (
                  <th key={area} className="th text-center">
                    <span className="block max-w-[92px] whitespace-normal leading-tight">
                      {titleCase(area)}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.entity_id}>
                  <td className="td sticky left-0 z-10 bg-white">
                    <Link className="link" to={`/entities/${e.entity_id}`}>
                      {e.name}
                    </Link>
                  </td>
                  {data.capability_areas.map((area) => {
                    const score = e.capability_scores?.[area] ?? 100
                    return (
                      <td
                        key={area}
                        className="px-2 py-2 text-center text-xs font-semibold tabular-nums"
                        style={{ background: scoreColour(score), color: scoreTextColour(score) }}
                        title={`${titleCase(area)}: ${score.toFixed(0)}/100`}
                      >
                        {score.toFixed(0)}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <Callout tone="info" title="How to read this page">
        Ranking is a triage aid: it tells a supervisor where to spend the next hour, not which
        organisation has failed. Open any organisation to see the plain-English reason behind its
        score, the exact records behind each finding, and a possible innocent explanation for every
        one of them.
      </Callout>
    </div>
  )
}
