const DEFAULT_ANNOTATION = {
  review_status: 'reviewed',
  topic_category: '',
  tags: '',
  hospitality_relevance: '',
  decision_lane: '',
  notes: '',
  summary_override: '',
}

export function annotationDraft(event) {
  const annotation = event?.annotation
  const classification = event?.classification
  return {
    ...DEFAULT_ANNOTATION,
    topic_category: annotation?.topic_category || classification?.topic_category || '',
    tags: (annotation?.tags || classification?.tags || []).join('，'),
    hospitality_relevance:
      annotation?.hospitality_relevance || classification?.hospitality_relevance || '',
    review_status: annotation?.review_status || DEFAULT_ANNOTATION.review_status,
    decision_lane: annotation?.decision_lane || '',
    notes: annotation?.notes || '',
    summary_override: annotation?.summary_override || '',
  }
}

export function annotationPayload(draft) {
  const tags = String(draft.tags || '')
    .split(/[,，]/)
    .map(tag => tag.trim())
    .filter((tag, index, values) => tag && values.indexOf(tag) === index)

  return {
    review_status: draft.review_status,
    topic_category: draft.topic_category?.trim() || null,
    tags,
    hospitality_relevance: draft.hospitality_relevance || null,
    decision_lane: draft.decision_lane || null,
    notes: draft.notes?.trim() || null,
    summary_override: draft.summary_override?.trim() || null,
  }
}

export function knowledgeConfigurationText(status) {
  if (status?.configured) return 'WeKnora 已连接'
  const missing = []
  if (!status?.base_url_configured) missing.push('服务地址')
  if (!status?.api_key_configured) missing.push('API Key')
  if (!status?.knowledge_base_id_configured) missing.push('知识库 ID')
  return `待配置：${missing.join('、') || '连接参数'}`
}
