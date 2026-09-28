import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../lib/api'
import { num, title as titleCase } from '../lib/format'
import { useApi } from '../lib/useApi'
import type { Overview } from '../lib/types'
import { BandChip, ErrorState, SectionTitle, Spinner } from '../components/ui'

export default function EntitiesPage() {
  const { data, loading, error, reload } = useApi<Overview>(() => api.overview(), [])
  const [query, setQuery] = useState('')

  const rows = useMemo(() => {
    const list = data?.entities || []
    if (!query.trim()) return list
    const q = query.toLowerCase()
    return list.filter(
      (e) =>
        e.name.toLowerCase().includes(q) ||
        e.entity_id.toLowerCase().includes(q) ||
        e.sector.toLowerCase().includes(q),
    )
  }, [data, query])

  if (loading) return <Spinner label="Loading organisations" />
  if (error) return <ErrorState message={error} onRetry={reload} />

  return (
    <div className="space-y-4">
      <SectionTitle
        title="Organisations"
        subtitle="Every critical-sector entity in the portfolio, with its submitted volumes."
        right={
          <input
            className="w-64 rounded-md border border-ink-300 px-3 py-1.5 text-sm"
            placeholder="Search name, ID or sector"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        }
      />
      <div className="card overflow-x-auto">
        <table className="w-full min-w-[900px]">
          <thead>
            <tr>
              <th className="th">Organisation</th>
              <th className="th">Sector</th>
              <th className="th">Tier</th>
              <th className="th">Analysts</th>
              <th className="th">Assets</th>
              <th className="th">Alerts</th>
              <th className="th">Cases</th>
              <th className="th">Escalations</th>
              <th className="th">Risk</th>
              <th className="th">Findings</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.entity_id} className="hover:bg-ink-50/60">
                <td className="td">
                  <Link className="link font-medium" to={`/entities/${e.entity_id}`}>
                    {e.name}
                  </Link>
                  <div className="mono text-ink-500">{e.entity_id}</div>
                </td>
                <td className="td">{titleCase(e.sector)}</td>
                <td className="td">{titleCase(e.size_tier)}</td>
                <td className="td tabular-nums">{num(e.analyst_count)}</td>
                <td className="td tabular-nums">{num(e.assets)}</td>
                <td className="td tabular-nums">{num(e.alerts)}</td>
                <td className="td tabular-nums">{num(e.cases)}</td>
                <td className="td tabular-nums">{num(e.escalations)}</td>
                <td className="td">
                  <BandChip band={e.risk_band} score={e.risk_score} />
                </td>
                <td className="td tabular-nums">{e.finding_count}</td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td className="td text-ink-500" colSpan={10}>
                  No organisation matches that search.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
