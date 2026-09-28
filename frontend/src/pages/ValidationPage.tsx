import { api } from '../lib/api'
import { num, pct } from '../lib/format'
import { useApi } from '../lib/useApi'
import type { ValidationResult } from '../lib/types'
import { Callout, ErrorState, SectionTitle, Spinner, StatTile } from '../components/ui'

export default function ValidationPage() {
  const { data, loading, error, reload } = useApi<ValidationResult>(() => api.validation(), [])

  if (loading) return <Spinner label="Scoring detections against ground truth" />
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data) return null

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-ink-900">Detection validation</h1>
        <p className="mt-1 text-sm text-ink-500">
          Measured against a synthetic corpus (seed {data.generator_seed}) in which every weakness
          was planted deliberately, so the correct answer is known exactly.
        </p>
      </div>

      <div className="card card-pad bg-navy-900 text-white">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-white/60">
          Headline result
        </p>
        <p className="mt-2 text-3xl font-semibold leading-snug">
          Planted {num(data.planted_total)} problems &mdash; detected {num(data.caught_total)} (
          {pct(data.recall, 1)} recall), precision {pct(data.precision, 1)}
        </p>
        <p className="mt-2 text-sm text-white/70">
          {num(data.missed_total)} missed, {num(data.false_positive_total)} false positives, across{' '}
          {num(data.findings_total)} findings in run <span className="mono">{data.run_id}</span>.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Recall" value={pct(data.recall, 1)} tone="accent" />
        <StatTile label="Precision" value={pct(data.precision, 1)} tone="accent" />
        <StatTile label="Planted problems" value={num(data.planted_total)} />
        <StatTile
          label="Detectors implemented"
          value={num(data.implemented_detectors.length)}
          hint="Only implemented detectors are scored"
        />
      </div>

      <section className="card overflow-x-auto">
        <div className="border-b border-ink-100 px-5 py-4">
          <SectionTitle
            title="Per-detector results"
            subtitle="Planted, caught, missed and false positives for every detector exercised by the corpus."
          />
        </div>
        <table className="w-full min-w-[900px]">
          <thead>
            <tr>
              <th className="th">Detector</th>
              <th className="th">Planted</th>
              <th className="th">Caught</th>
              <th className="th">Missed</th>
              <th className="th">False positives</th>
              <th className="th">Recall</th>
              <th className="th">Precision</th>
              <th className="th">Notes</th>
            </tr>
          </thead>
          <tbody>
            {data.per_detector.map((row) => (
              <tr key={row.detector_id} className="hover:bg-ink-50/60">
                <td className="td mono font-semibold">{row.detector_id}</td>
                <td className="td tabular-nums">{row.planted}</td>
                <td className="td tabular-nums text-risk-low">{row.caught}</td>
                <td className="td tabular-nums text-risk-high">{row.missed || ''}</td>
                <td className="td tabular-nums text-risk-medium">{row.false_positives || ''}</td>
                <td className="td tabular-nums">{row.recall === null ? '-' : pct(row.recall)}</td>
                <td className="td tabular-nums">
                  {row.precision === null ? '-' : pct(row.precision)}
                </td>
                <td className="td text-xs text-ink-500">
                  {row.missed_entities.length > 0 && (
                    <span className="mr-2">missed: {row.missed_entities.join(', ')}</span>
                  )}
                  {row.false_positive_entities.length > 0 && (
                    <span>false positive: {row.false_positive_entities.join(', ')}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card card-pad">
          <SectionTitle
            title="Innocent look-alikes"
            subtitle="Organisations built to look suspicious while being perfectly sound. These must NOT be flagged."
          />
          <ul className="space-y-3">
            {data.innocent_lookalikes.map((la) => (
              <li key={la.entity_id} className="rounded-md border border-ink-100 p-3">
                <div className="flex items-center gap-2">
                  <span
                    className={`chip ${
                      la.correctly_not_flagged
                        ? 'border-risk-low/30 bg-risk-lowbg text-risk-low'
                        : 'border-risk-high/30 bg-risk-highbg text-risk-high'
                    }`}
                  >
                    {la.correctly_not_flagged ? 'correctly not flagged' : 'incorrectly flagged'}
                  </span>
                  <span className="text-sm font-medium">{la.name}</span>
                  <span className="mono text-ink-500">{la.entity_id}</span>
                </div>
                <p className="mt-2 text-sm text-ink-700">{la.why}</p>
                {la.flagged_by.length > 0 && (
                  <p className="mt-1 text-xs text-risk-high">
                    Flagged by: {la.flagged_by.join(', ')}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>

        <section className="card card-pad">
          <SectionTitle
            title="Healthy organisations"
            subtitle="Reference SOCs with no planted weakness. A clean sheet here is what keeps the ranking trustworthy."
          />
          <ul className="space-y-2">
            {data.healthy_entities.map((h) => (
              <li key={h.entity_id} className="flex items-center gap-2 text-sm">
                <span
                  className={`chip ${
                    h.correctly_not_flagged
                      ? 'border-risk-low/30 bg-risk-lowbg text-risk-low'
                      : 'border-risk-high/30 bg-risk-highbg text-risk-high'
                  }`}
                >
                  {h.correctly_not_flagged ? 'clean' : 'flagged'}
                </span>
                <span className="mono">{h.entity_id}</span>
                {h.flagged_by.length > 0 && (
                  <span className="text-xs text-risk-high">{h.flagged_by.join(', ')}</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      </div>

      <Callout tone="info" title="How validation works">
        {data.methodology}
      </Callout>
    </div>
  )
}
