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

const PLATFORM_LABELS = {
  douyin: '抖音',
  weibo: '微博',
  bilibili: 'B站',
  xiaohongshu: '小红书',
}

const LIFECYCLE_LABELS = {
  emerging: '萌芽',
  rising: '上升',
  peaking: '峰值',
  declining: '回落',
  dormant: '沉寂',
  recurring: '复燃',
}

const LIFECYCLE_TONES = {
  emerging: 'cyan',
  rising: 'emerald',
  peaking: 'amber',
  declining: 'slate',
  dormant: 'muted',
  recurring: 'violet',
}

const RELEVANCE_LABELS = {
  relevant: '高度相关',
  possibly_relevant: '可能相关',
  irrelevant: '不相关',
}

export function platformStatusLabel(status) {
  return STATUS_LABELS[status] || '未知'
}

export function platformStatusTone(status) {
  return STATUS_TONES[status] || 'muted'
}

export function platformName(platform) {
  return PLATFORM_LABELS[platform] || platform || '未知平台'
}

export function lifecycleLabel(state) {
  return LIFECYCLE_LABELS[state] || state || '未知'
}

export function lifecycleTone(state) {
  return LIFECYCLE_TONES[state] || 'muted'
}

export function relevanceLabel(value) {
  return RELEVANCE_LABELS[value] || '未分类'
}

export function formatAgeMinutes(minutes) {
  if (minutes === null || minutes === undefined) return '无采集记录'
  if (minutes <= 0) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  const remainder = minutes % 60
  return remainder ? `${hours} 小时 ${remainder} 分钟前` : `${hours} 小时前`
}

export function formatTimestamp(value) {
  if (!value) return '时间未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

export function summarizePlatformHealth(platforms = []) {
  const summary = { fresh: 0, stale: 0, failed: 0, unavailable: 0, total: platforms.length }
  for (const platform of platforms) {
    const status = Object.hasOwn(summary, platform?.status) ? platform.status : 'unavailable'
    summary[status] += 1
  }
  summary.attention = summary.stale + summary.failed
  return summary
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
