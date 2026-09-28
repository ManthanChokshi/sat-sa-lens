import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { api } from '../lib/api'
import { num, shortDate, title as titleCase, trendArrow } from '../lib/format'
import { useApi } from '../lib/useApi'
import type { EntityDetail, ReviewSample } from '../lib/types'
import {
  BandChip,
  Callout,
  ConfidenceBar,
  EmptyState,
  ErrorState,
  GapChip,
  SectionTitle,
  Spinner,
  StatTile,
  StatusChip,
  SeverityChip,
} from '../components/ui'

export default function EntityPage() {
  const { entityId = '' } = useParams()
  const { data, loading, error, reload } = useApi<EntityDetail>(
    () => api.entity(entityId),
    [entityId],
  )
  const [sample, setSample] = useState<ReviewSample | null>(null)
  const [sampleSize, setSampleSize] = useState(50)
  const [sampling, setSampling] = useState(false)

  const timeline = useMemo(
    () =>
      (data?.timeline || []).map((t) => ({
        day: String(t.day).slice(0, 10),
        alerts: t.alerts,
        critical: t.critical,
        high: t.high,
      })),
    [data],
  )

  if (loading) return <Spinner label="Loading organisation" />
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data) return null

  const s = data.scores || {}
  const arrow = trendArrow(s.trend_direction || 'flat')
  const groups = Object.entries(data.findings_by_capability || {})

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link className="link text-sm" to="/">
            &larr; Portfolio overview
          </Link>
          <h1 className="mt-1 text-xl font-semibold text-ink-900">{data.entity.name}</h1>
          <p className="mt-1 text-sm text-ink-500">
            <span className="mono">{data.entity.entity_id}</span>
            <span className="mx-2 text-ink-300">|</span>
            {titleCase(data.entity.sector)}
            <span className="mx-2 text-ink-300">|</span>
            {titleCase(data.entity.size_tier)} tier
            <span className="mx-2 text-ink-300">|</span>
            {data.entity.analyst_count} analysts
            <span className="mx-2 text-ink-300">|</span>
            peer group {data.peer_group.label} (compared at {data.peer_group.comparison_level})
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link className="btn-ghost" to={`/negative-space?entity=${data.entity.entity_id}`}>
            Negative space
          </Link>
          <a className="btn-primary" href={api.reportUrl(data.entity.entity_id)}>
            Download evidence pack (PDF)
          </a>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card card-pad">
          <p className="label">Risk score</p>
          <div className="mt-2 flex items-end gap-3">
            <span className="text-5xl font-semibold tabular-nums text-ink-900">
              {(s.risk_score ?? 0).toFixed(0)}
            </span>
            <BandChip band={s.risk_band || 'Low'} />
            <span className={`text-lg ${arrow.cls}`} title={arrow.label}>
              {arrow.glyph}
            </span>
          </div>
          <p className="mt-2 text-xs text-ink-500">
            {s.finding_count ?? 0} open or confirmed findings. {arrow.label}.
          </p>
        </div>
        <div className="card card-pad lg:col-span-2">
          <p className="label">Top reasons, in plain English</p>
          {(s.top_contributors || []).length ? (
            <ol className="mt-2 space-y-2">
              {s.top_contributors.map((c, i) => (
                <li key={c.finding_id} className="flex gap-3 text-sm">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-ink-100 text-[11px] font-semibold">
                    {i + 1}
                  </span>
                  <span>
                    <Link className="link font-medium" to={`/findings/${c.finding_id}`}>
                      {c.title}
                    </Link>
                    <span className="ml-2 text-xs text-ink-500">
                      {c.detector_id} &middot; {c.severity} &middot; {(c.confidence * 100).toFixed(0)}%
                      confidence &middot; {c.weight.toFixed(0)} points
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-2 text-sm text-ink-500">
              Nothing was flagged for this organisation in the latest run.
            </p>
          )}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <StatTile label="Assets" value={num(data.counts.assets)} hint={`${num(data.counts.critical_assets)} critical`} />
        <StatTile label="Alerts" value={num(data.counts.alerts)} />
        <StatTile label="Cases" value={num(data.counts.cases)} />
        <StatTile label="Escalations" value={num(data.counts.escalations)} />
        <StatTile label="Submissions" value={num(data.submissions.length)} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card card-pad">
          <SectionTitle
            title="Capability scorecard"
            subtitle="This organisation against the average of its peer group. 100 = no concerns."
          />
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={data.radar} outerRadius="72%">
                <PolarGrid stroke="#e5e7eb" />
                <PolarAngleAxis dataKey="label" tick={{ fontSize: 10, fill: '#6b7280' }} />
                <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 9, fill: '#9ca3af' }} />
                <Radar
                  name="Peer average"
                  dataKey="peer_average"
                  stroke="#9ca3af"
                  fill="#9ca3af"
                  fillOpacity={0.18}
                />
                <Radar
                  name={data.entity.entity_id}
                  dataKey="entity"
                  stroke="#1f6feb"
                  fill="#1f6feb"
                  fillOpacity={0.35}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Tooltip contentStyle={{ fontSize: 12 }} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="card card-pad">
          <SectionTitle
            title="Alerts per day"
            subtitle="The submitted alert volume across the reporting period, with critical and high alerts called out."
          />
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timeline} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                <CartesianGrid stroke="#f3f4f6" />
                <XAxis dataKey="day" tick={{ fontSize: 10, fill: '#9ca3af' }} minTickGap={28} />
                <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} />
                <Tooltip contentStyle={{ fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Area
                  type="monotone"
                  dataKey="alerts"
                  name="All alerts"
                  stroke="#1f6feb"
                  fill="#dbeafe"
                />
                <Area
                  type="monotone"
                  dataKey="high"
                  name="High"
                  stroke="#b45309"
                  fill="#fde68a"
                  fillOpacity={0.6}
                />
                <Area
                  type="monotone"
                  dataKey="critical"
                  name="Critical"
                  stroke="#b91c1c"
                  fill="#fecaca"
                  fillOpacity={0.7}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>
      </div>

      <section className="space-y-4">
        <SectionTitle
          title="Findings by capability area"
          subtitle="Each one is a hypothesis with its numbers, its evidence and a possible innocent explanation."
        />
        {!groups.length && (
          <EmptyState
            title="No findings for this organisation"
            body="The first pass found nothing to escalate for this submission. That is a good sign, not a guarantee - use the review sample below to check records the tool did not flag."
          />
        )}
        {groups.map(([area, items]) => (
          <div key={area} className="card">
            <div className="flex items-center justify-between border-b border-ink-100 px-5 py-3">
              <h3 className="text-sm font-semibold text-ink-900">{titleCase(area)}</h3>
              <span className="text-xs text-ink-500">
                score {(s.capability_scores?.[area] ?? 100).toFixed(0)}/100 &middot; {items.length}{' '}
                finding{items.length === 1 ? '' : 's'}
              </span>
            </div>
            <ul className="divide-y divide-ink-100">
              {items.map((f) => (
                <li key={f.finding_id} className="px-5 py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link className="link text-sm font-semibold" to={`/findings/${f.finding_id}`}>
                      {f.title}
                    </Link>
                    <SeverityChip severity={f.severity} />
                    <GapChip gap={f.gap_type} />
                    <StatusChip status={f.status} />
                    <span className="mono text-ink-500">{f.detector_id}</span>
                  </div>
                  <p className="mt-2 line-clamp-2 text-sm text-ink-700">{f.rationale}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-ink-500">
                    <ConfidenceBar value={f.confidence} />
                    <span>{num(f.evidence_count)} evidence records</span>
                    {f.supervisor_note && <span>Note: {f.supervisor_note}</span>}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>

      <section className="card card-pad">
        <SectionTitle
          title="Generate a review sample"
          subtitle="70% of the sample is the highest-risk evidence; 30% is a seeded random control so the review can also say something about records the tool did not flag."
        />
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <span className="label block">Sample size</span>
            <input
              type="number"
              min={5}
              max={500}
              value={sampleSize}
              onChange={(e) => setSampleSize(Number(e.target.value))}
              className="mt-1 w-28 rounded-md border border-ink-300 px-2 py-1.5 text-sm"
            />
          </label>
          <button
            className="btn-primary"
            disabled={sampling}
            onClick={async () => {
              setSampling(true)
              try {
                setSample(await api.reviewSample(entityId, sampleSize))
              } finally {
                setSampling(false)
              }
            }}
          >
            {sampling ? 'Selecting records...' : 'Generate review sample'}
          </button>
          {sample && (
            <a className="btn-ghost" href={api.sampleCsvUrl(sample.sample_id)}>
              Export CSV
            </a>
          )}
        </div>
        {sample && (
          <div className="mt-4">
            <p className="text-sm text-ink-700">
              Sample <span className="mono">{sample.sample_id}</span>: {sample.actual_size} records
              ({sample.coverage.risk_picks} highest-risk, {sample.coverage.random_picks} random,
              seed {sample.seed}). This organisation has {num(sample.coverage.entity_cases_total)}{' '}
              cases, of which {num(sample.coverage.cases_referenced_by_findings)} are referenced by
              at least one finding.
            </p>
            <div className="mt-3 max-h-80 overflow-auto rounded-md border border-ink-100">
              <table className="w-full">
                <thead className="sticky top-0">
                  <tr>
                    <th className="th">Record</th>
                    <th className="th">Table</th>
                    <th className="th">Bucket</th>
                    <th className="th">Why it was picked</th>
                  </tr>
                </thead>
                <tbody>
                  {sample.items.map((item) => (
                    <tr key={`${item.row_table}-${item.row_id}`}>
                      <td className="td mono">{item.row_id}</td>
                      <td className="td">{item.row_table}</td>
                      <td className="td">
                        <span
                          className={`chip ${
                            item.bucket === 'highest_risk'
                              ? 'border-accent-300 bg-accent-50 text-accent-700'
                              : 'border-ink-300 bg-ink-100 text-ink-700'
                          }`}
                        >
                          {item.bucket === 'highest_risk' ? 'highest risk' : 'random control'}
                        </span>
                      </td>
                      <td className="td text-ink-700">{item.pick_reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card card-pad">
          <SectionTitle title="Declared commitments" subtitle="What this organisation says it does." />
          <table className="w-full">
            <thead>
              <tr>
                <th className="th">Metric</th>
                <th className="th">Target</th>
              </tr>
            </thead>
            <tbody>
              {data.commitments.map((c) => (
                <tr key={c.metric}>
                  <td className="td">{titleCase(c.metric)}</td>
                  <td className="td tabular-nums">
                    {c.threshold} {c.unit}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="card card-pad">
          <SectionTitle title="Submissions" subtitle="Declared counts and integrity status per period." />
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr>
                  <th className="th">Period</th>
                  <th className="th">Declared</th>
                  <th className="th">Integrity</th>
                  <th className="th">Hash</th>
                </tr>
              </thead>
              <tbody>
                {data.submissions.map((sub) => (
                  <tr key={String(sub.submission_id)}>
                    <td className="td">
                      {shortDate(String(sub.period_start))} &rarr; {shortDate(String(sub.period_end))}
                    </td>
                    <td className="td tabular-nums">{num(Number(sub.declared_alert_count))}</td>
                    <td className="td">
                      <span
                        className={`chip ${
                          sub.integrity_status === 'count_mismatch'
                            ? 'border-risk-high/30 bg-risk-highbg text-risk-high'
                            : 'border-risk-low/30 bg-risk-lowbg text-risk-low'
                        }`}
                      >
                        {String(sub.integrity_status)}
                      </span>
                    </td>
                    <td className="td mono text-ink-500">{String(sub.file_hash).slice(0, 12)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <Callout tone="warn" title="This is a first pass, not a verdict">
        The score above reflects only what is visible in this submission. Confirm or dismiss each
        finding on its own page; dismissed findings are removed from the score immediately and the
        change is written to the audit log.
      </Callout>
    </div>
  )
}
