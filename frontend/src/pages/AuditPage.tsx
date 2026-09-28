import { api } from '../lib/api'
import { num, shortDate } from '../lib/format'
import { useApi } from '../lib/useApi'
import type { AuditPayload } from '../lib/types'
import { Callout, ErrorState, SectionTitle, Spinner } from '../components/ui'

export default function AuditPage() {
  const { data, loading, error, reload } = useApi<AuditPayload>(() => api.audit(), [])

  if (loading) return <Spinner label="Loading audit trail" />
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data) return null

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-ink-900">Audit log</h1>
        <p className="mt-1 text-sm text-ink-500">
          Every analysis run and every supervisor action, with the code version and input data hash
          that produced it. The same data and the same code version always produce the same findings.
        </p>
      </div>

      <section className="card overflow-x-auto">
        <div className="border-b border-ink-100 px-5 py-4">
          <SectionTitle title="Analysis runs" />
        </div>
        <table className="w-full min-w-[1000px]">
          <thead>
            <tr>
              <th className="th">Run</th>
              <th className="th">Started</th>
              <th className="th">Status</th>
              <th className="th">Code</th>
              <th className="th">Rules</th>
              <th className="th">Commit</th>
              <th className="th">Seed</th>
              <th className="th">Data hash</th>
              <th className="th">Findings</th>
              <th className="th">Notes</th>
            </tr>
          </thead>
          <tbody>
            {data.runs.map((r) => (
              <tr key={r.run_id} className="hover:bg-ink-50/60">
                <td className="td mono">{r.run_id}</td>
                <td className="td whitespace-nowrap">{shortDate(r.started_at)}</td>
                <td className="td">
                  <span
                    className={`chip ${
                      r.status === 'complete'
                        ? 'border-risk-low/30 bg-risk-lowbg text-risk-low'
                        : 'border-ink-300 bg-ink-100 text-ink-700'
                    }`}
                  >
                    {r.status}
                  </span>
                </td>
                <td className="td mono">{r.code_version}</td>
                <td className="td mono">{r.rules_version}</td>
                <td className="td mono">{r.git_commit}</td>
                <td className="td tabular-nums">{r.random_seed}</td>
                <td className="td mono text-ink-500" title={r.data_hash}>
                  {String(r.data_hash || '').slice(0, 16)}
                </td>
                <td className="td tabular-nums">{num(r.finding_count)}</td>
                <td className="td text-xs text-ink-500">{r.notes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card overflow-x-auto">
        <div className="border-b border-ink-100 px-5 py-4">
          <SectionTitle title="Actions" subtitle="Ingest, uploads, status changes, exports." />
        </div>
        <table className="w-full min-w-[900px]">
          <thead>
            <tr>
              <th className="th">When</th>
              <th className="th">Actor</th>
              <th className="th">Action</th>
              <th className="th">Object</th>
              <th className="th">Detail</th>
            </tr>
          </thead>
          <tbody>
            {data.actions.map((a) => (
              <tr key={a.audit_id} className="hover:bg-ink-50/60">
                <td className="td whitespace-nowrap">{shortDate(a.ts)}</td>
                <td className="td">{a.actor}</td>
                <td className="td mono">{a.action}</td>
                <td className="td mono text-ink-500">
                  {a.object_type}
                  {a.object_id ? `: ${a.object_id}` : ''}
                </td>
                <td className="td text-ink-700">{a.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <Callout tone="info" title="Reproducibility">
        Each run records the code version, the rule-set version, the git commit, the random seed and
        a hash of the exact input data. Re-running the analysis on unchanged data produces byte-for-byte
        identical findings, which is what makes an assessment defensible months later.
      </Callout>
    </div>
  )
}
