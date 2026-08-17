const STATUS_LABELS = {
  fresh: '实时',
  stale: '陈旧',
  failed: '采集失败',
  unavailable: '暂无数据',
}

const STATUS_TONES = {
  fresh: 'success',
  stale: 'warning',
  failed: 'danger',
  unavailable: 'muted',
}

export function platformStatusLabel(status) {
  return STATUS_LABELS[status] || '未知'
}

export function platformStatusTone(status) {
  return STATUS_TONES[status] || 'muted'
}

export function formatAgeMinutes(minutes) {
  if (minutes === null || minutes === undefined) return '无采集记录'
  if (minutes <= 0) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  const remainder = minutes % 60
  return remainder ? `${hours} 小时 ${remainder} 分钟前` : `${hours} 小时前`
}

export function buildEventQuery(filters) {
  const params = new URLSearchParams()
  for (const key of ['q', 'platform', 'lifecycle', 'hospitality_relevance', 'data_quality']) {
    const value = typeof filters[key] === 'string' ? filters[key].trim() : filters[key]
    if (value) params.set(key, value)
  }
  params.set('limit', String(filters.limit ?? 20))
  params.set('offset', String(filters.offset ?? 0))
  return params.toString()
}
