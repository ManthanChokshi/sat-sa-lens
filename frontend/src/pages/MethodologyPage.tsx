import { api } from '../lib/api'
import { gapLabel, title as titleCase } from '../lib/format'
import { useApi } from '../lib/useApi'
import type { DetectorInfo, Stats } from '../lib/types'
import { Callout, ErrorState, SectionTitle, Spinner } from '../components/ui'

export default function MethodologyPage() {
  const detectors = useApi<DetectorInfo[]>(() => api.detectors(), [])
  const stats = useApi<Stats>(() => api.stats(), [])

  if (detectors.loading) return <Spinner label="Loading methodology" />
  if (detectors.error) return <ErrorState message={detectors.error} onRetry={detectors.reload} />

  const groups: Record<string, DetectorInfo[]> = {}
  ;(detectors.data || []).forEach((d) => {
    groups[d.gap_type] = groups[d.gap_type] || []
    groups[d.gap_type].push(d)
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-ink-900">Methodology</h1>
        <p className="mt-1 text-sm text-ink-500">
          What each detector looks for, how organisations are compared, and the guarantees the tool
          gives a supervisor.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Callout tone="info" title="Execution gaps">
          The organisation looks effective on paper, but the operational record disagrees: criticals
          closed in seconds, no escalation, copy-paste notes, closures bunched against an SLA.
        </Callout>
        <Callout tone="info" title="Negative space">
          Evidence that should exist and does not: critical assets with no telemetry, attack
          categories every peer reports, volume that collapses, records that do not join up.
        </Callout>
        <Callout tone="info" title="Unknown patterns">
          An unsupervised model flags organisations whose whole profile is unlike their peers, so the
          tool is not limited to the weaknesses someone thought to write a rule for.
        </Callout>
      </div>

      {Object.entries(groups).map(([gap, items]) => (
        <section key={gap} className="card overflow-x-auto">
          <div className="border-b border-ink-100 px-5 py-4">
            <SectionTitle title={gapLabel[gap as keyof typeof gapLabel] || titleCase(gap)} />
          </div>
          <table className="w-full min-w-[860px]">
            <thead>
              <tr>
                <th className="th">ID</th>
                <th className="th">Name</th>
                <th className="th">What it catches</th>
                <th className="th">Capability area</th>
                <th className="th">Min sample</th>
                <th className="th">Version</th>
              </tr>
            </thead>
            <tbody>
              {items.map((d) => (
                <tr key={d.detector_id}>
                  <td className="td mono font-semibold">{d.detector_id}</td>
                  <td className="td mono">{d.name}</td>
                  <td className="td text-ink-700">{d.description}</td>
                  <td className="td">{titleCase(d.capability_area)}</td>
                  <td className="td tabular-nums">{d.min_sample}</td>
                  <td className="td mono text-ink-500">{d.version}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}

      <section className="card card-pad">
        <SectionTitle title="Fair comparison" />
        <ul className="list-inside list-disc space-y-1 text-sm text-ink-700">
          <li>
            The peer group is sector plus size tier. When that group is too small to be meaningful,
            the comparison widens to the sector, then the size tier, then the whole portfolio - and
            every finding records which level was used.
          </li>
          <li>
            Rates are normalised per asset, per analyst and per 1,000 alerts, so a large bank is
            never penalised for volume.
          </li>
          <li>
            Small samples are protected with a minimum record count and a Wilson lower bound, so a
            tiny organisation is not flagged on three records.
          </li>
          <li>
            Confidence never reaches 1.0. Every finding is a hypothesis for a human to confirm.
          </li>
        </ul>
      </section>

      {stats.data && (
        <section className="card card-pad">
          <SectionTitle title="Current dataset" />
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-5">
            {Object.entries(stats.data.counts).map(([k, v]) => (
              <div key={k} className="rounded-md border border-ink-100 bg-ink-50/60 p-3">
                <p className="text-[11px] font-medium text-ink-500">{titleCase(k)}</p>
                <p className="mt-1 text-lg font-semibold tabular-nums">{v.toLocaleString()}</p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-ink-500">
            Reporting period {String(stats.data.period?.start).slice(0, 10)} to{' '}
            {String(stats.data.period?.end).slice(0, 10)} &middot; {stats.data.detectors} detectors
            registered.
          </p>
        </section>
      )}
    </div>
  )
}
