import { describe, expect, it } from 'vitest'

import {
  bandClass,
  formatMetricValue,
  gapLabel,
  metricLabel,
  num,
  pct,
  scoreColour,
  severityClass,
  title,
  trendArrow,
} from '../format'

describe('formatters', () => {
  it('renders percentages and counts', () => {
    expect(pct(0.7789, 1)).toBe('77.9%')
    expect(pct(null)).toBe('-')
    expect(num(186548)).toBe('186,548')
    expect(num(undefined)).toBe('-')
  })

  it('humanises identifiers', () => {
    expect(title('threat_detection')).toBe('Threat Detection')
    expect(metricLabel('share_closed_under_2_min')).toBe('Share closed under 2 min')
    expect(metricLabel('sla_minutes')).toBe('SLA minutes')
  })

  it('formats metric values without losing precision that matters', () => {
    expect(formatMetricValue(2000)).toBe('2,000')
    expect(formatMetricValue(0.7789)).toBe('0.7789')
    expect(formatMetricValue(15.72)).toBe('15.72')
    expect(formatMetricValue(true)).toBe('yes')
    expect(formatMetricValue(null)).toBe('-')
  })

  it('maps risk bands and severities to distinct styles', () => {
    expect(bandClass('High')).not.toBe(bandClass('Low'))
    expect(severityClass('high')).not.toBe(severityClass('low'))
  })

  it('colours capability scores from green to red', () => {
    expect(scoreColour(100)).toBe('#dcfce7')
    expect(scoreColour(20)).toBe('#fca5a5')
  })

  it('labels every gap type', () => {
    expect(Object.keys(gapLabel).sort()).toEqual([
      'anomaly',
      'data_quality',
      'execution_gap',
      'negative_space',
    ])
  })

  it('points the trend arrow the right way', () => {
    expect(trendArrow('worsening').glyph).toBe('▲')
    expect(trendArrow('improving').glyph).toBe('▼')
    expect(trendArrow('flat').label).toMatch(/unchanged/i)
  })
})
