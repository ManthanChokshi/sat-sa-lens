export type GapType = 'execution_gap' | 'negative_space' | 'anomaly' | 'data_quality'
export type FindingSeverity = 'high' | 'medium' | 'low'
export type FindingStatus = 'open' | 'valid' | 'not_valid'
export type RiskBand = 'High' | 'Medium' | 'Low'

export interface Run {
  run_id: string
  started_at: string
  finished_at: string | null
  code_version: string
  rules_version: string
  git_commit: string
  data_hash: string
  random_seed: number
  detector_versions: string
  finding_count: number
  entity_count: number
  row_counts: string
  status: string
  notes: string
}

export interface Finding {
  finding_id: string
  run_id: string
  entity_id: string
  entity_name?: string
  sector?: string
  size_tier?: string
  detector_id: string
  detector_version: string
  gap_type: GapType
  capability_area: string
  severity: FindingSeverity
  confidence: number
  title: string
  rationale: string
  innocent_explanation: string
  metrics: Record<string, unknown>
  evidence_row_ids: string[]
  evidence_count: number
  evidence_table: string
  status: FindingStatus
  supervisor_note: string
  created_at: string
  detector?: DetectorInfo
}

export interface DetectorInfo {
  detector_id: string
  name: string
  version: string
  gap_type: GapType
  capability_area: string
  min_sample: number
  description: string
}

export interface Contributor {
  finding_id: string
  detector_id: string
  title: string
  severity: FindingSeverity
  confidence: number
  gap_type: GapType
  capability_area: string
  weight: number
}

export interface TrendPoint {
  window: string
  period_start: string
  period_end: string
  risk_score: number
  risk_band: RiskBand
}

export interface OverviewEntity {
  entity_id: string
  name: string
  sector: string
  size_tier: string
  analyst_count: number
  assets: number
  alerts: number
  cases: number
  escalations: number
  submissions: number
  risk_score: number
  risk_band: RiskBand
  finding_count: number
  dismissed_findings: number
  counts_by_gap_type: Record<string, number>
  counts_by_severity: Record<string, number>
  capability_scores: Record<string, number>
  trend: TrendPoint[]
  trend_direction: 'worsening' | 'improving' | 'flat'
  top_contributors: Contributor[]
}

export interface Overview {
  run: Run | null
  entities: OverviewEntity[]
  capability_areas: string[]
  sectors: string[]
  kpis: {
    entities_assessed: number
    high_risk_entities: number
    medium_risk_entities: number
    open_findings: number
    validated_findings: number
    dismissed_findings: number
    execution_gaps: number
    negative_space: number
    anomalies: number
    data_quality: number
    high_severity_findings: number
  }
}

export interface RadarPoint {
  area: string
  label: string
  entity: number
  peer_average: number
}

export interface EntityDetail {
  entity: {
    entity_id: string
    name: string
    sector: string
    size_tier: string
    analyst_count: number
  }
  counts: Record<string, number>
  run: Run | null
  scores: {
    risk_score: number
    risk_band: RiskBand
    total_weight: number
    finding_count: number
    counts_by_gap_type: Record<string, number>
    counts_by_severity: Record<string, number>
    top_contributors: Contributor[]
    capability_scores: Record<string, number>
    capability_explanations: Record<string, Contributor[]>
    trend: TrendPoint[]
    trend_direction: string
  }
  radar: RadarPoint[]
  peer_group: {
    label: string
    comparison_level: string
    peers: { entity_id: string; name: string; risk_score: number }[]
  }
  findings: Finding[]
  findings_by_capability: Record<string, Finding[]>
  timeline: { day: string; alerts: number; critical: number; high: number }[]
  commitments: { metric: string; threshold: number; unit: string }[]
  submissions: Record<string, unknown>[]
}

export interface EvidencePage {
  finding_id: string
  evidence_table: string
  total: number
  offset?: number
  limit?: number
  rows: Record<string, unknown>[]
  columns: string[]
  note?: string
}

export interface NegativeSpace {
  entity_id: string
  comparison_level: string
  critical_assets: {
    asset_id: string
    hostname: string
    asset_type: string
    criticality: string
    environment: string
    alerts: number
    last_alert: string | null
  }[]
  silent_critical_assets: NegativeSpace['critical_assets']
  categories: {
    category: string
    entity_alerts: number
    entity_share: number
    peers_reporting: number
    peer_count: number
    peer_presence: number
    missing: boolean
  }[]
  missing_categories: NegativeSpace['categories']
  related_findings: Finding[]
}

export interface ValidationResult {
  run_id: string
  generator_seed: number
  planted_total: number
  caught_total: number
  missed_total: number
  false_positive_total: number
  recall: number
  precision: number
  findings_total: number
  methodology: string
  implemented_detectors: string[]
  per_detector: {
    detector_id: string
    implemented: boolean
    planted: number
    caught: number
    missed: number
    false_positives: number
    recall: number | null
    precision: number | null
    caught_entities: string[]
    missed_entities: string[]
    false_positive_entities: string[]
    findings_produced: number
  }[]
  innocent_lookalikes: {
    entity_id: string
    name: string
    why: string
    flagged_by: string[]
    correctly_not_flagged: boolean
  }[]
  healthy_entities: {
    entity_id: string
    flagged_by: string[]
    correctly_not_flagged: boolean
  }[]
}

export interface ReviewSample {
  sample_id: string
  entity_id: string
  run_id: string
  requested_size: number
  actual_size: number
  seed: number
  risk_share: number
  items: {
    row_id: string
    row_table: string
    bucket: 'highest_risk' | 'random'
    risk_weight: number
    pick_reason: string
  }[]
  coverage: Record<string, number>
}

export interface UploadStage {
  upload_id: string
  entity_id: string
  table_type: string
  filename: string
  file_sha256: string
  rows: number
  columns: string[]
  preview: Record<string, string>[]
  suggestion: {
    table_type: string
    mapping: Record<string, string | null>
    confidence: Record<string, number>
    unmapped_columns: string[]
    missing_required: string[]
    value_map: Record<string, Record<string, string>>
    reused_saved_mapping: boolean
    profile: {
      column: string
      samples: string[]
      distinct_values: number
      null_share: number
      inferred_kind: string
      distinct_list: string[]
    }[]
  }
}

export interface QualityReport {
  entity_id: string
  run_id: string
  overall: 'green' | 'amber' | 'red'
  checks: {
    check: string
    label: string
    status: 'green' | 'amber' | 'red'
    title: string
    rationale: string
    metrics: Record<string, unknown>
  }[]
}

export interface AuditPayload {
  runs: Run[]
  actions: {
    audit_id: string
    ts: string
    actor: string
    action: string
    object_type: string
    object_id: string
    detail: string
  }[]
}

export interface Stats {
  counts: Record<string, number>
  period: { start: string | null; end: string | null }
  latest_run: Run | null
  detectors: number
}
