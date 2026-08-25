import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildEventQuery,
  formatAgeMinutes,
  formatTimestamp,
  lifecycleLabel,
  lifecycleTone,
  platformName,
  platformStatusLabel,
  platformStatusTone,
  relevanceLabel,
  summarizePlatformHealth,
} from '../src/utils/hotspotDashboard.js'


test('buildEventQuery omits empty filters and keeps paging', () => {
  assert.equal(
    buildEventQuery({
      q: ' 台风 ',
      platform: 'weibo',
      lifecycle: '',
      hospitality_relevance: 'relevant',
      limit: 20,
      offset: 0,
    }),
    'q=%E5%8F%B0%E9%A3%8E&platform=weibo&hospitality_relevance=relevant&limit=20&offset=0',
  )
})


test('freshness helpers never describe unavailable or failed data as realtime', () => {
  assert.equal(platformStatusLabel('fresh'), '实时')
  assert.equal(platformStatusLabel('stale'), '陈旧')
  assert.equal(platformStatusLabel('failed'), '采集失败')
  assert.equal(platformStatusLabel('unavailable'), '暂无数据')
  assert.equal(platformStatusTone('fresh'), 'success')
  assert.equal(platformStatusTone('stale'), 'warning')
  assert.equal(platformStatusTone('failed'), 'danger')
  assert.equal(platformStatusTone('unavailable'), 'muted')
})


test('formatAgeMinutes makes data age explicit', () => {
  assert.equal(formatAgeMinutes(null), '无采集记录')
  assert.equal(formatAgeMinutes(0), '刚刚')
  assert.equal(formatAgeMinutes(45), '45 分钟前')
  assert.equal(formatAgeMinutes(150), '2 小时 30 分钟前')
})


test('dashboard labels keep domain vocabulary consistent', () => {
  assert.equal(platformName('xiaohongshu'), '小红书')
  assert.equal(platformName('unknown'), 'unknown')
  assert.equal(lifecycleLabel('rising'), '上升')
  assert.equal(lifecycleTone('recurring'), 'violet')
  assert.equal(relevanceLabel('relevant'), '高度相关')
  assert.equal(relevanceLabel(null), '未分类')
})


test('platform health summary preserves stale and failed truthfully', () => {
  assert.deepEqual(
    summarizePlatformHealth([
      { status: 'fresh' },
      { status: 'stale' },
      { status: 'failed' },
      { status: 'unexpected' },
    ]),
    { fresh: 1, stale: 1, failed: 1, unavailable: 1, total: 4, attention: 2 },
  )
})


test('formatTimestamp does not invent invalid timestamps', () => {
  assert.equal(formatTimestamp(null), '时间未知')
  assert.equal(formatTimestamp('not-a-date'), '时间未知')
  assert.notEqual(formatTimestamp('2026-08-21T10:30:00+08:00'), '时间未知')
})
