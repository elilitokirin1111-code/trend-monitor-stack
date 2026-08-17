<template>
  <div class="space-y-4 md:space-y-6">
    <section v-if="store.error" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
      <i class="fas fa-triangle-exclamation mr-2"></i>{{ store.error }}
    </section>

    <section class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <article
        v-for="platform in platformCards"
        :key="platform.platform"
        class="glass rounded-xl p-4"
      >
        <div class="flex items-start justify-between gap-3">
          <div>
            <p class="text-sm font-semibold text-white">{{ platformName(platform.platform) }}</p>
            <p class="mt-1 text-xs text-gray-500">{{ formatAgeMinutes(platform.data_age_minutes) }}</p>
          </div>
          <span :class="['rounded-full px-2.5 py-1 text-xs font-medium', statusClass(platform.status)]">
            {{ platformStatusLabel(platform.status) }}
          </span>
        </div>
        <div class="mt-4 space-y-1 text-xs text-gray-400">
          <p>Provider：<span class="text-gray-300">{{ platform.winning_provider_id || '未成功采集' }}</span></p>
          <p>Fallback：<span :class="platform.fallback_used ? 'text-amber-300' : 'text-gray-300'">{{ platform.fallback_used ? '已启用' : '未触发' }}</span></p>
          <p v-if="platform.stale_reason" class="break-all text-amber-300">原因：{{ reasonLabel(platform.stale_reason) }}</p>
          <p v-if="platform.error" class="break-words text-red-300">{{ platform.error.code || platform.error.kind }}：{{ platform.error.message }}</p>
        </div>
      </article>
    </section>

    <section class="glass rounded-xl p-4 md:p-5">
      <div class="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div class="grid flex-1 grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <label class="text-xs text-gray-400 lg:col-span-2">
            搜索事件
            <input v-model="filters.q" @keyup.enter="applyFilters" class="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-amber-500/50" placeholder="输入热点标题" />
          </label>
          <label class="text-xs text-gray-400">
            平台
            <select v-model="filters.platform" class="mt-1 w-full rounded-lg border border-white/10 bg-gray-900/80 px-3 py-2 text-sm text-white">
              <option value="">全部平台</option>
              <option v-for="platform in platforms" :key="platform" :value="platform">{{ platformName(platform) }}</option>
            </select>
          </label>
          <label class="text-xs text-gray-400">
            生命周期
            <select v-model="filters.lifecycle" class="mt-1 w-full rounded-lg border border-white/10 bg-gray-900/80 px-3 py-2 text-sm text-white">
              <option value="">全部阶段</option>
              <option v-for="state in lifecycleOptions" :key="state" :value="state">{{ lifecycleLabel(state) }}</option>
            </select>
          </label>
          <label class="text-xs text-gray-400">
            酒旅相关性
            <select v-model="filters.hospitality_relevance" class="mt-1 w-full rounded-lg border border-white/10 bg-gray-900/80 px-3 py-2 text-sm text-white">
              <option value="">全部相关性</option>
              <option value="relevant">相关</option>
              <option value="possibly_relevant">可能相关</option>
              <option value="irrelevant">不相关</option>
            </select>
          </label>
        </div>
        <button @click="applyFilters" :disabled="store.loading" class="rounded-lg bg-gradient-to-r from-amber-500 to-orange-500 px-5 py-2 text-sm font-medium text-white disabled:opacity-50">
          <i :class="[store.loading ? 'fa-spinner animate-spin' : 'fa-filter', 'fas mr-2']"></i>筛选
        </button>
      </div>
    </section>

    <section class="glass overflow-hidden rounded-xl">
      <header class="flex flex-col gap-2 border-b border-white/10 p-4 sm:flex-row sm:items-center sm:justify-between md:px-5">
        <div>
          <h2 class="font-semibold text-white">聚合热点事件</h2>
          <p class="mt-1 text-xs text-gray-500">最新趋势运行 · 共 {{ store.events.total || 0 }} 个事件</p>
        </div>
        <div class="text-xs text-gray-500">
          趋势状态：<span :class="overviewStatusClass">{{ overviewStatusText }}</span>
        </div>
      </header>

      <div v-if="store.loading" class="space-y-3 p-5">
        <div v-for="index in 4" :key="index" class="skeleton h-28 rounded-xl"></div>
      </div>
      <div v-else-if="!store.overview?.has_data" class="p-10 text-center">
        <i class="fas fa-database mb-3 block text-4xl text-gray-600"></i>
        <p class="text-sm text-gray-300">尚无真实热点快照</p>
        <p class="mt-2 text-xs text-gray-500">等待 Collector 完成首次生产采集；系统不会用演示数据填充这里。</p>
      </div>
      <div v-else-if="store.events.items.length === 0" class="p-10 text-center text-sm text-gray-500">
        当前筛选条件下没有事件
      </div>
      <div v-else class="divide-y divide-white/5">
        <button
          v-for="event in store.events.items"
          :key="event.event_id"
          class="block w-full p-4 text-left transition hover:bg-white/5 md:p-5"
          @click="store.openEvent(event.event_id)"
        >
          <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <span class="rounded-md bg-amber-500/15 px-2 py-1 text-xs text-amber-300">{{ lifecycleLabel(event.lifecycle_state) }}</span>
                <span :class="['rounded-md px-2 py-1 text-xs', event.data_quality === 'complete' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-300']">{{ event.data_quality === 'complete' ? '数据完整' : '数据部分缺失' }}</span>
                <span v-for="platform in event.platforms" :key="platform" class="rounded-md bg-white/5 px-2 py-1 text-xs text-gray-400">{{ platformName(platform) }}</span>
              </div>
              <h3 class="mt-3 text-base font-medium text-white">{{ event.canonical_title }}</h3>
              <p v-if="event.classification?.summary" class="mt-2 line-clamp-2 text-sm text-gray-400">{{ event.classification.summary }}</p>
              <p v-else class="mt-2 text-xs text-gray-500">AI 分类未生成或已跳过，不补写推测结果。</p>
            </div>
            <div class="flex gap-5 text-xs lg:text-right">
              <div><p class="text-gray-500">趋势分</p><p class="mt-1 text-base font-semibold text-white">{{ number(event.trend_score) }}</p></div>
              <div><p class="text-gray-500">酒旅相关</p><p class="mt-1 text-sm font-medium text-amber-300">{{ relevanceLabel(event.classification?.hospitality_relevance) }}</p></div>
              <div><p class="text-gray-500">原始观测</p><p class="mt-1 text-base font-semibold text-white">{{ event.observation_count }}</p></div>
            </div>
          </div>
        </button>
      </div>

      <footer v-if="store.events.total > filters.limit" class="flex items-center justify-between border-t border-white/10 px-4 py-3 text-sm md:px-5">
        <button :disabled="filters.offset === 0" @click="page(-1)" class="text-gray-400 disabled:opacity-30">上一页</button>
        <span class="text-xs text-gray-500">{{ filters.offset + 1 }}–{{ Math.min(filters.offset + filters.limit, store.events.total) }} / {{ store.events.total }}</span>
        <button :disabled="filters.offset + filters.limit >= store.events.total" @click="page(1)" class="text-gray-400 disabled:opacity-30">下一页</button>
      </footer>
    </section>

    <div v-if="store.detailLoading || store.selectedEvent" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3 backdrop-blur-sm" @click.self="store.closeEvent()">
      <div class="glass max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-2xl p-4 md:p-6">
        <div v-if="store.detailLoading" class="p-12 text-center text-gray-400"><i class="fas fa-spinner mr-2 animate-spin"></i>加载证据链...</div>
        <template v-else-if="store.selectedEvent">
          <header class="flex items-start justify-between gap-4">
            <div>
              <p class="text-xs text-amber-300">{{ lifecycleLabel(store.selectedEvent.lifecycle_state) }} · 趋势分 {{ number(store.selectedEvent.trend_score) }}</p>
              <h2 class="mt-2 text-xl font-semibold text-white">{{ store.selectedEvent.canonical_title }}</h2>
            </div>
            <button class="text-gray-500 hover:text-white" @click="store.closeEvent()"><i class="fas fa-times"></i></button>
          </header>
          <div class="mt-5 grid gap-4 md:grid-cols-3">
            <div class="rounded-xl bg-white/5 p-4 md:col-span-2">
              <p class="text-xs text-gray-500">AI 摘要</p>
              <p class="mt-2 text-sm leading-6 text-gray-300">{{ store.selectedEvent.classification?.summary || '未生成分类摘要。' }}</p>
              <p v-if="store.selectedEvent.classification?.rationale" class="mt-3 border-t border-white/10 pt-3 text-xs leading-5 text-gray-500">判定依据：{{ store.selectedEvent.classification.rationale }}</p>
            </div>
            <div class="rounded-xl bg-white/5 p-4 text-sm">
              <p class="text-xs text-gray-500">酒旅相关性</p>
              <p class="mt-2 font-medium text-amber-300">{{ relevanceLabel(store.selectedEvent.classification?.hospitality_relevance) }}</p>
              <p class="mt-3 text-xs text-gray-500">置信度：{{ percent(store.selectedEvent.classification?.confidence) }}</p>
            </div>
          </div>
          <section class="mt-6">
            <h3 class="font-medium text-white">原始证据（{{ store.selectedEvent.evidence.length }}）</h3>
            <div class="mt-3 space-y-2">
              <article v-for="item in store.selectedEvent.evidence" :key="item.raw_item_id" class="rounded-xl border border-white/10 bg-white/5 p-3">
                <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div class="min-w-0">
                    <p class="text-xs text-gray-500">{{ platformName(item.platform) }} · {{ item.provider_id }} · #{{ item.rank ?? '-' }} · {{ item.freshness === 'fresh' ? '实时采集' : '陈旧数据' }}</p>
                    <p class="mt-1 text-sm text-gray-200">{{ item.title }}</p>
                    <p class="mt-1 break-all text-xs text-gray-600">Raw ID: {{ item.raw_item_id }}</p>
                  </div>
                  <div class="flex flex-shrink-0 gap-2 text-xs">
                    <a :href="item.source_url" target="_blank" rel="noopener noreferrer" class="rounded-lg bg-white/10 px-3 py-2 text-gray-300 hover:text-white">原平台</a>
                    <a :href="item.raw_item_url" target="_blank" rel="noopener noreferrer" class="rounded-lg bg-amber-500/15 px-3 py-2 text-amber-300">原始记录</a>
                  </div>
                </div>
              </article>
            </div>
          </section>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive } from 'vue'

import { useHotspotDashboardStore } from '../stores/hotspotDashboard'
import { formatAgeMinutes, platformStatusLabel } from '../utils/hotspotDashboard'

const store = useHotspotDashboardStore()
const platforms = ['douyin', 'weibo', 'bilibili', 'xiaohongshu']
const lifecycleOptions = ['emerging', 'rising', 'peaking', 'declining', 'dormant', 'recurring']
const filters = reactive({ q: '', platform: '', lifecycle: '', hospitality_relevance: '', data_quality: '', limit: 20, offset: 0 })

const platformCards = computed(() => store.overview?.platforms || platforms.map(platform => ({ platform, status: 'unavailable', data_age_minutes: null, attempts: [] })))
const overviewStatusText = computed(() => store.overview?.trend_run ? (store.overview.trend_run.status === 'partial' ? '部分数据' : '完整') : '未运行')
const overviewStatusClass = computed(() => store.overview?.trend_run?.status === 'partial' ? 'text-amber-300' : store.overview?.trend_run ? 'text-emerald-300' : 'text-gray-500')

function applyFilters() { filters.offset = 0; store.refresh(filters) }
function page(direction) { filters.offset = Math.max(0, filters.offset + direction * filters.limit); store.refresh(filters) }
function platformName(value) { return { douyin: '抖音', weibo: '微博', bilibili: 'B站', xiaohongshu: '小红书' }[value] || value }
function lifecycleLabel(value) { return { emerging: '萌芽', rising: '上升', peaking: '峰值', declining: '回落', dormant: '沉寂', recurring: '复燃' }[value] || value || '未知' }
function relevanceLabel(value) { return { relevant: '相关', possibly_relevant: '可能相关', irrelevant: '不相关' }[value] || '未分类' }
function reasonLabel(value) { return { no_collection_run: '尚无采集记录', snapshot_age_exceeded: '快照已超过时效阈值', latest_collection_failed: '最近一次采集失败' }[value] || value }
function statusClass(value) { return { fresh: 'bg-emerald-500/15 text-emerald-300', stale: 'bg-amber-500/15 text-amber-300', failed: 'bg-red-500/15 text-red-300', unavailable: 'bg-white/5 text-gray-500' }[value] || 'bg-white/5 text-gray-500' }
function number(value) { return value === null || value === undefined ? '-' : Number(value).toFixed(2) }
function percent(value) { return value === null || value === undefined ? '未提供' : `${Math.round(Number(value) * 100)}%` }

onMounted(() => store.refresh(filters))
</script>
