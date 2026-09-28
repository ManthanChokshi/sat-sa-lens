import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import EvidenceTable from '../components/EvidenceTable'
import { api } from '../lib/api'
import { formatMetricValue, metricLabel, num, title as titleCase } from '../lib/format'
import { useApi } from '../lib/useApi'
import type { EvidencePage, Finding } from '../lib/types'
import {
  Callout,
  ConfidenceBar,
  ErrorState,
  GapChip,
  SectionTitle,
  SeverityChip,
  Spinner,
  StatusChip,
} from '../components/ui'

export default function FindingPage() {
  const { findingId = '' } = useParams()
  const finding = useApi<Finding>(() => api.finding(findingId), [findingId])
  const evidence = useApi<EvidencePage>(() => api.evidence(findingId, 300), [findingId])
  const [note, setNote] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState<string | null>(null)

  if (finding.loading) return <Spinner label="Loading finding" />
  if (finding.error) return <ErrorState message={finding.error} onRetry={finding.reload} />
  const f = finding.data
  if (!f) return null

  const noteValue = note ?? f.supervisor_note ?? ''
  const setStatus = async (status: 'valid' | 'not_valid' | 'open') => {
    setSaving(true)
    try {
      await api.patchFinding(f.finding_id, { status, supervisor_note: noteValue })
      setSaved(
        status === 'valid'
          ? 'Marked valid. It still counts toward the risk score.'
          : status === 'not_valid'
            ? 'Dismissed. It has been removed from the risk score.'
            : 'Reopened.',
      )
      finding.reload()
    } finally {
      setSaving(false)
    }
  }

  const scalarMetrics = Object.entries(f.metrics || {}).filter(
    ([, v]) => v === null || ['string', 'number', 'boolean'].includes(typeof v),
  )
  const complexMetrics = Object.entries(f.metrics || {}).filter(
    ([, v]) => v !== null && !['string', 'number', 'boolean'].includes(typeof v),
  )

  return (
    <div className="space-y-6">
      <div>
        <Link className="link text-sm" to={`/entities/${f.entity_id}`}>
          &larr; {f.entity_name || f.entity_id}
        </Link>
        <h1 className="mt-1 text-xl font-semibold text-ink-900">{f.title}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <SeverityChip severity={f.severity} />
          <GapChip gap={f.gap_type} />
          <StatusChip status={f.status} />
          <span className="chip border-ink-300 bg-white text-ink-700">
            {titleCase(f.capability_area)}
          </span>
          <span className="mono text-ink-500">
            {f.detector_id} v{f.detector_version}
          </span>
          <ConfidenceBar value={f.confidence} />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <section className="card card-pad lg:col-span-2">
          <SectionTitle title="What the data shows" />
          <p className="text-sm leading-relaxed text-ink-700">{f.rationale}</p>
          {f.detector?.description && (
            <p className="mt-3 border-t border-ink-100 pt-3 text-xs text-ink-500">
              <strong>How this detector works:</strong> {f.detector.description}
            </p>
          )}
        </section>
        <Callout tone="warn" title="Possible innocent explanation">
          {f.innocent_explanation}
        </Callout>
      </div>

      <section className="card card-pad">
        <SectionTitle
          title="The numbers behind it"
          subtitle="Including the peer baseline used for the comparison."
        />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
          {scalarMetrics.map(([key, value]) => (
            <div key={key} className="rounded-md border border-ink-100 bg-ink-50/60 p-3">
              <p className="text-[11px] font-medium leading-tight text-ink-500">
                {metricLabel(key)}
              </p>
              <p className="mt-1 break-words text-sm font-semibold tabular-nums text-ink-900">
                {formatMetricValue(value)}
              </p>
            </div>
          ))}
        </div>
        {complexMetrics.length > 0 && (
          <details className="mt-4">
            <summary className="cursor-pointer text-sm font-medium text-accent-600">
              Show detailed breakdown ({complexMetrics.length} structured metrics)
            </summary>
            <pre className="mono mt-2 max-h-80 overflow-auto rounded-md bg-ink-900 p-3 text-[11px] text-ink-100">
              {JSON.stringify(Object.fromEntries(complexMetrics), null, 2)}
            </pre>
          </details>
        )}
      </section>

      <section className="card card-pad">
        <SectionTitle
          title="Supervisor decision"
          subtitle="Only a supervisor changes a finding's status. Dismissed findings stop counting toward the risk score."
        />
        <textarea
          className="w-full rounded-md border border-ink-300 p-3 text-sm"
          rows={3}
          placeholder="Optional note: what you checked, who you spoke to, what you concluded."
          value={noteValue}
          onChange={(e) => setNote(e.target.value)}
        />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button className="btn-ok" disabled={saving} onClick={() => setStatus('valid')}>
            Confirm valid
          </button>
          <button className="btn-danger" disabled={saving} onClick={() => setStatus('not_valid')}>
            Not valid
          </button>
          {f.status !== 'open' && (
            <button className="btn-ghost" disabled={saving} onClick={() => setStatus('open')}>
              Reopen
            </button>
          )}
          {saved && <span className="text-sm text-ink-500">{saved}</span>}
        </div>
      </section>

      <section className="card card-pad">
        <SectionTitle
          title="Evidence"
          subtitle={`The exact records behind this finding${
            f.metrics?.evidence_rows_total
              ? ` - ${num(Number(f.metrics.evidence_rows_total))} records referenced`
              : ''
          }.`}
        />
        {evidence.loading && <Spinner label="Loading evidence" />}
        {evidence.error && <ErrorState message={evidence.error} onRetry={evidence.reload} />}
        {evidence.data && <EvidenceTable page={evidence.data} />}
      </section>
    </div>
  )
}
