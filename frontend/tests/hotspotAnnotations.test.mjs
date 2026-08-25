import assert from 'node:assert/strict'
import test from 'node:test'

import {
  annotationDraft,
  annotationPayload,
  knowledgeConfigurationText,
} from '../src/utils/hotspotAnnotations.js'

test('annotation draft prefers human review while using AI as an initial suggestion', () => {
  const draft = annotationDraft({
    classification: { topic_category: 'AI 分类', tags: ['AI 标签'] },
    annotation: { topic_category: '人工分类', tags: ['人工标签'], revision: 2 },
  })
  assert.equal(draft.topic_category, '人工分类')
  assert.equal(draft.tags, '人工标签')
})

test('annotation payload trims, deduplicates and separates Chinese or western commas', () => {
  const payload = annotationPayload({
    review_status: 'reviewed',
    topic_category: ' 酒店营销 ',
    tags: '暑期, 酒店，暑期',
    hospitality_relevance: 'relevant',
    decision_lane: '',
    notes: ' ',
    summary_override: '人工摘要',
  })
  assert.deepEqual(payload.tags, ['暑期', '酒店'])
  assert.equal(payload.topic_category, '酒店营销')
  assert.equal(payload.decision_lane, null)
  assert.equal(payload.notes, null)
})

test('knowledge configuration text never exposes credentials', () => {
  assert.equal(
    knowledgeConfigurationText({
      configured: false,
      base_url_configured: true,
      api_key_configured: false,
      knowledge_base_id_configured: false,
    }),
    '待配置：API Key、知识库 ID',
  )
})
