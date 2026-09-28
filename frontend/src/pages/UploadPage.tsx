import { useEffect, useMemo, useState } from 'react'

import { api } from '../lib/api'
import { num, pct, title as titleCase } from '../lib/format'
import { useApi } from '../lib/useApi'
import type { Overview, QualityReport, UploadStage } from '../lib/types'
import { Callout, ErrorState, SectionTitle, Spinner } from '../components/ui'

const TABLE_TYPES = ['alerts', 'cases', 'assets', 'escalations', 'submissions', 'commitments']

export default function UploadPage() {
  const overview = useApi<Overview>(() => api.overview(), [])
  const [entityId, setEntityId] = useState('')
  const [tableType, setTableType] = useState('alerts')
  const [file, setFile] = useState<File | null>(null)
  const [stage, setStage] = useState<UploadStage | null>(null)
  const [mapping, setMapping] = useState<Record<string, string | null>>({})
  const [valueMap, setValueMap] = useState<Record<string, Record<string, string>>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{
    rows_loaded: number
    rows_replaced: number
    submission_id: string | null
    quality_report: QualityReport
  } | null>(null)

  useEffect(() => {
    if (!entityId && overview.data?.entities.length) {
      setEntityId(overview.data.entities[0].entity_id)
    }
  }, [entityId, overview.data])

  const missingRequired = useMemo(() => {
    if (!stage) return []
    return stage.suggestion.missing_required.filter((f) => !mapping[f])
  }, [stage, mapping])

  const doStage = async () => {
    if (!file || !entityId) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const staged = await api.stageUpload(entityId, tableType, file)
      setStage(staged)
      setMapping(staged.suggestion.mapping)
      setValueMap(staged.suggestion.value_map || {})
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const doCommit = async () => {
    if (!stage) return
    setBusy(true)
    setError(null)
    try {
      setResult(await api.commitUpload(stage.upload_id, mapping, valueMap))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (overview.loading) return <Spinner label="Loading organisations" />

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-ink-900">Upload a submission</h1>
        <p className="mt-1 text-sm text-ink-500">
          Organisations export their SOC records in whatever format their tooling produces. Upload
          the file as-is; the tool profiles it, proposes a mapping onto the canonical schema and
          remembers your confirmation for next time.
        </p>
      </div>

      <section className="card card-pad">
        <SectionTitle title="1. Choose the file" />
        <div className="grid gap-4 md:grid-cols-4">
          <label className="text-sm">
            <span className="label block">Organisation</span>
            <select
              className="mt-1 w-full rounded-md border border-ink-300 px-2 py-1.5 text-sm"
              value={entityId}
              onChange={(e) => setEntityId(e.target.value)}
            >
              {(overview.data?.entities || []).map((e) => (
                <option key={e.entity_id} value={e.entity_id}>
                  {e.name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="label block">Record type</span>
            <select
              className="mt-1 w-full rounded-md border border-ink-300 px-2 py-1.5 text-sm"
              value={tableType}
              onChange={(e) => setTableType(e.target.value)}
            >
              {TABLE_TYPES.map((t) => (
                <option key={t} value={t}>
                  {titleCase(t)}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm md:col-span-2">
            <span className="label block">File (CSV, TSV or JSON)</span>
            <input
              type="file"
              accept=".csv,.tsv,.json,.tab"
              className="mt-1 w-full rounded-md border border-ink-300 px-2 py-1.5 text-sm"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
        </div>
        <button className="btn-primary mt-4" onClick={doStage} disabled={!file || busy}>
          {busy && !stage ? 'Profiling file...' : 'Profile file and suggest mapping'}
        </button>
        {error && <div className="mt-3"><ErrorState message={error} /></div>}
      </section>

      {stage && (
        <>
          <section className="card card-pad">
            <SectionTitle
              title="2. Confirm the column mapping"
              subtitle={`${num(stage.rows)} rows, ${stage.columns.length} columns. SHA-256 ${stage.file_sha256.slice(0, 24)}...`}
              right={
                stage.suggestion.reused_saved_mapping ? (
                  <span className="chip border-risk-low/30 bg-risk-lowbg text-risk-low">
                    reused this organisation&apos;s saved mapping
                  </span>
                ) : undefined
              }
            />
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {Object.keys(stage.suggestion.mapping).map((field) => {
                const confidence = stage.suggestion.confidence[field] ?? 0
                return (
                  <label key={field} className="rounded-md border border-ink-100 p-3 text-sm">
                    <span className="flex items-center justify-between">
                      <span className="font-medium">{titleCase(field)}</span>
                      <span
                        className={`text-[11px] ${
                          confidence >= 0.8
                            ? 'text-risk-low'
                            : confidence >= 0.5
                              ? 'text-risk-medium'
                              : 'text-ink-500'
                        }`}
                      >
                        {confidence > 0 ? `${pct(confidence)} match` : 'not matched'}
                      </span>
                    </span>
                    <select
                      className="mt-2 w-full rounded-md border border-ink-300 px-2 py-1.5 text-sm"
                      value={mapping[field] ?? ''}
                      onChange={(e) =>
                        setMapping({ ...mapping, [field]: e.target.value || null })
                      }
                    >
                      <option value="">- not present in this file -</option>
                      {stage.columns.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </label>
                )
              })}
            </div>
            {missingRequired.length > 0 && (
              <div className="mt-4">
                <Callout tone="warn" title="Required fields are still unmapped">
                  {missingRequired.map(titleCase).join(', ')}. Map them before importing.
                </Callout>
              </div>
            )}

            {Object.keys(valueMap).length > 0 && (
              <div className="mt-6">
                <SectionTitle
                  title="Severity value mapping"
                  subtitle="Vendor labels are mapped onto the canonical five-level scale."
                />
                {Object.entries(valueMap).map(([field, values]) => (
                  <div key={field} className="grid gap-2 md:grid-cols-3 lg:grid-cols-5">
                    {Object.entries(values).map(([raw, canonical]) => (
                      <label key={raw} className="rounded-md border border-ink-100 p-2 text-sm">
                        <span className="mono block text-ink-500">{raw}</span>
                        <select
                          className="mt-1 w-full rounded-md border border-ink-300 px-2 py-1 text-sm"
                          value={canonical}
                          onChange={(e) =>
                            setValueMap({
                              ...valueMap,
                              [field]: { ...values, [raw]: e.target.value },
                            })
                          }
                        >
                          {['critical', 'high', 'medium', 'low', 'info'].map((v) => (
                            <option key={v} value={v}>
                              {v}
                            </option>
                          ))}
                        </select>
                      </label>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="card card-pad">
            <SectionTitle title="3. Preview the first 20 rows" />
            <div className="overflow-x-auto rounded-md border border-ink-100">
              <table className="w-full">
                <thead>
                  <tr>
                    {stage.columns.map((c) => (
                      <th key={c} className="th whitespace-nowrap">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {stage.preview.map((row, i) => (
                    <tr key={i}>
                      {stage.columns.map((c) => (
                        <td key={c} className="td mono max-w-[260px] truncate">
                          {String(row[c] ?? '')}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button
              className="btn-primary mt-4"
              onClick={doCommit}
              disabled={busy || missingRequired.length > 0}
            >
              {busy ? 'Importing...' : `Import ${num(stage.rows)} rows`}
            </button>
            <p className="mt-2 text-xs text-ink-500">
              Importing replaces this organisation&apos;s existing {tableType} rows, pseudonymises
              analyst names, usernames and IP addresses, records the file hash, and runs the
              data-quality checks.
            </p>
          </section>
        </>
      )}

      {result && (
        <section className="card card-pad">
          <SectionTitle
            title="Data-quality report card"
            subtitle={`${num(result.rows_loaded)} rows imported (replacing ${num(result.rows_replaced)}).${
              result.submission_id ? ` Recorded as submission ${result.submission_id}.` : ''
            }`}
            right={
              <span
                className={`chip ${
                  result.quality_report.overall === 'green'
                    ? 'border-risk-low/30 bg-risk-lowbg text-risk-low'
                    : result.quality_report.overall === 'amber'
                      ? 'border-risk-medium/30 bg-risk-mediumbg text-risk-medium'
                      : 'border-risk-high/30 bg-risk-highbg text-risk-high'
                }`}
              >
                overall: {result.quality_report.overall}
              </span>
            }
          />
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {result.quality_report.checks.map((c) => (
              <div
                key={c.check}
                className={`rounded-md border p-3 ${
                  c.status === 'green'
                    ? 'border-risk-low/30 bg-risk-lowbg'
                    : c.status === 'amber'
                      ? 'border-risk-medium/30 bg-risk-mediumbg'
                      : 'border-risk-high/30 bg-risk-highbg'
                }`}
              >
                <p className="text-sm font-semibold text-ink-900">
                  <span className="mono mr-2">{c.check}</span>
                  {c.label}
                </p>
                <p className="mt-1 text-xs text-ink-700">{c.rationale || c.title}</p>
              </div>
            ))}
          </div>
          <Callout tone="info" title="Next step">
            Press <strong>Run analysis</strong> in the header to re-score this organisation against
            its peer group with the newly imported data.
          </Callout>
        </section>
      )}
    </div>
  )
}
