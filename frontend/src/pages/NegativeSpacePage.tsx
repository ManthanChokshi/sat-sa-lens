import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { api } from '../lib/api'
import { num, pct, title as titleCase } from '../lib/format'
import { useApi } from '../lib/useApi'
import type { NegativeSpace, Overview } from '../lib/types'
import {
  Callout,
  ErrorState,
  GapChip,
  SectionTitle,
  SeverityChip,
  Spinner,
} from '../components/ui'

export default function NegativeSpacePage() {
  const [params, setParams] = useSearchParams()
  const overview = useApi<Overview>(() => api.overview(), [])
  const [entityId, setEntityId] = useState(params.get('entity') || '')

  useEffect(() => {
    if (!entityId && overview.data?.entities.length) {
      setEntityId(overview.data.entities[0].entity_id)
    }
  }, [entityId, overview.data])

  const ns = useApi<NegativeSpace>(
    () => (entityId ? api.negativeSpace(entityId) : Promise.resolve(null as never)),
    [entityId],
  )

  if (overview.loading) return <Spinner label="Loading organisations" />
  if (overview.error) return <ErrorState message={overview.error} onRetry={overview.reload} />

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Negative space"
        subtitle="Evidence that should exist and does not: critical assets with no telemetry, and whole attack categories every peer reports."
        right={
          <select
            className="rounded-md border border-ink-300 px-2 py-1.5 text-sm"
            value={entityId}
            onChange={(e) => {
              setEntityId(e.target.value)
              setParams({ entity: e.target.value })
            }}
          >
            {(overview.data?.entities || []).map((e) => (
              <option key={e.entity_id} value={e.entity_id}>
                {e.name}
              </option>
            ))}
          </select>
        }
      />

      {ns.loading && <Spinner label="Building coverage matrices" />}
      {ns.error && <ErrorState message={ns.error} onRetry={ns.reload} />}
      {ns.data && (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <section className="card card-pad">
              <SectionTitle
                title="Critical and high assets: alert activity"
                subtitle={`${ns.data.silent_critical_assets.length} of ${ns.data.critical_assets.length} produced one alert or fewer for the whole period.`}
              />
              <div className="max-h-96 overflow-auto rounded-md border border-ink-100">
                <table className="w-full">
                  <thead className="sticky top-0">
                    <tr>
                      <th className="th">Host</th>
                      <th className="th">Type</th>
                      <th className="th">Criticality</th>
                      <th className="th">Env</th>
                      <th className="th">Alerts</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ns.data.critical_assets.map((a) => {
                      const silent = a.alerts <= 1
                      return (
                        <tr key={a.asset_id} className={silent ? 'bg-risk-highbg' : ''}>
                          <td className="td mono">{a.hostname}</td>
                          <td className="td">{a.asset_type}</td>
                          <td className="td">{a.criticality}</td>
                          <td className="td">{a.environment}</td>
                          <td
                            className={`td tabular-nums font-semibold ${
                              silent ? 'text-risk-high' : 'text-ink-700'
                            }`}
                          >
                            {a.alerts}
                            {silent && <span className="ml-2 text-xs font-normal">silent</span>}
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
                title="Attack-category coverage vs peer group"
                subtitle={`Compared at the ${ns.data.comparison_level} level. A highlighted row is a category this organisation never reports but its peers do.`}
              />
              <div className="max-h-96 overflow-auto rounded-md border border-ink-100">
                <table className="w-full">
                  <thead className="sticky top-0">
                    <tr>
                      <th className="th">Category</th>
                      <th className="th">Alerts here</th>
                      <th className="th">Share</th>
                      <th className="th">Peers reporting</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ns.data.categories.map((c) => (
                      <tr key={c.category} className={c.missing ? 'bg-risk-highbg' : ''}>
                        <td className="td">{titleCase(c.category)}</td>
                        <td
                          className={`td tabular-nums ${
                            c.missing ? 'font-semibold text-risk-high' : ''
                          }`}
                        >
                          {num(c.entity_alerts)}
                        </td>
                        <td className="td tabular-nums text-ink-500">{pct(c.entity_share, 2)}</td>
                        <td className="td tabular-nums">
                          {c.peers_reporting}/{c.peer_count}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <section className="card card-pad">
            <SectionTitle
              title="Related negative-space findings"
              subtitle="Open one to see the reasoning, the numbers and the exact records."
            />
            {ns.data.related_findings.length ? (
              <ul className="divide-y divide-ink-100">
                {ns.data.related_findings.map((f) => (
                  <li key={f.finding_id} className="py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link className="link text-sm font-semibold" to={`/findings/${f.finding_id}`}>
                        {f.title}
                      </Link>
                      <SeverityChip severity={f.severity} />
                      <GapChip gap={f.gap_type} />
                      <span className="mono text-ink-500">{f.detector_id}</span>
                    </div>
                    <p className="mt-1 text-sm text-ink-700">{f.rationale}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-ink-500">
                No negative-space findings for this organisation in the latest run.
              </p>
            )}
          </section>

          <Callout tone="info" title="Why negative space matters">
            An organisation under pressure to look effective can tune down noisy detections or leave
            an asset unmonitored. Nothing in an alert feed shows that directly - it shows up as
            absence. This page makes the absence visible and always offers the benign reading first:
            a quiet host may simply be new, isolated, or covered by a tool that was not submitted.
          </Callout>
        </>
      )}
    </div>
  )
}
