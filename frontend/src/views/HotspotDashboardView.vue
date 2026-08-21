<template>
  <div class="intelligence-page">
    <section v-if="store.error" class="truth-alert truth-alert--danger">
      <i class="fas fa-triangle-exclamation"></i>
      <div><strong>情报读取失败</strong><p>{{ store.error }}</p></div>
    </section>

    <section v-if="health.attention > 0" class="truth-alert truth-alert--warning">
      <i class="fas fa-shield-halved"></i>
      <div>
        <strong>{{ health.attention }} 个平台需要关注</strong>
        <p>陈旧或失败数据已被明确标记，当前页面不会将缓存结果描述为实时热点。</p>
      </div>
    </section>

    <PlatformHealthStrip
      :platforms="platformCards"
      :active-platform="filters.platform"
      @select="selectPlatform"
    />

    <section class="overview-panel">
      <div class="overview-copy">
        <div class="overview-kicker">
          <span class="live-indicator"><span></span>最新聚合窗口</span>
          <span>{{ formatTimestamp(store.overview?.generated_at) }}</span>
        </div>
        <h1>从平台热榜中，识别值得行动的事件</h1>
        <p>聚合四个平台的真实采集结果，保留来源证据，重点呈现趋势阶段、数据质量与酒旅相关性。</p>
      </div>
      <div class="overview-run">
        <span>趋势运行</span>
        <strong :class="overviewStatusTone">{{ overviewStatusText }}</strong>
        <small>{{ store.overview?.trend_run?.algorithm_version || '尚无算法版本' }}</small>
      </div>
    </section>

    <section class="metric-grid" aria-label="最新情报指标">
      <article class="metric-card">
        <div class="metric-icon metric-icon--gold"><i class="fas fa-layer-group"></i></div>
        <div><p>聚合事件</p><strong>{{ store.overview?.event_count ?? 0 }}</strong><span>当前趋势运行</span></div>
      </article>
      <article class="metric-card">
        <div class="metric-icon metric-icon--green"><i class="fas fa-signal"></i></div>
        <div><p>实时平台</p><strong>{{ health.fresh }}<small>/{{ health.total || 4 }}</small></strong><span>{{ platformHealthSummary }}</span></div>
      </article>
      <article class="metric-card">
        <div class="metric-icon metric-icon--blue"><i class="fas fa-circle-nodes"></i></div>
        <div><p>完整事件</p><strong>{{ store.overview?.trend_run?.complete_count ?? 0 }}</strong><span>{{ store.overview?.trend_run ? `部分数据 ${store.overview.trend_run.partial_count}` : '尚无趋势运行' }}</span></div>
      </article>
      <article class="metric-card">
        <div class="metric-icon metric-icon--violet"><i class="fas fa-clock-rotate-left"></i></div>
        <div><p>最近研判</p><strong class="metric-card__time">{{ formatTimestamp(store.overview?.trend_run?.evaluated_at) }}</strong><span>以持久化快照为准</span></div>
      </article>
    </section>

    <section class="workspace-panel">
      <header class="workspace-header">
        <div>
          <p class="section-kicker">INTELLIGENCE QUEUE</p>
          <h2>事件研判队列</h2>
          <span>共 {{ store.events.total || 0 }} 个事件，点击任意事件查看跨平台证据链</span>
        </div>
        <div class="view-actions">
          <button type="button" :class="{ active: displayMode === 'dense' }" title="紧凑列表" @click="displayMode = 'dense'"><i class="fas fa-bars-staggered"></i></button>
          <button type="button" :class="{ active: displayMode === 'cards' }" title="卡片浏览" @click="displayMode = 'cards'"><i class="fas fa-table-cells-large"></i></button>
          <button type="button" :class="['filter-toggle', { active: showFilters || hasAdvancedFilters }]" aria-label="筛选事件" @click="showFilters = !showFilters">
            <i class="fas fa-sliders"></i><span>筛选</span>
          </button>
        </div>
      </header>

      <div class="quick-filter-row">
        <div class="quick-filters" aria-label="趋势阶段快捷筛选">
          <button
            v-for="option in quickLifecycleOptions"
            :key="option.value || 'all'"
            type="button"
            :class="{ active: filters.lifecycle === option.value }"
            @click="setLifecycle(option.value)"
          >
            {{ option.label }}
          </button>
        </div>
        <label class="event-search">
          <i class="fas fa-magnifying-glass"></i>
          <input v-model="filters.q" type="search" aria-label="搜索事件标题" placeholder="搜索事件标题" @keyup.enter="applyFilters" />
          <button v-if="filters.q" type="button" aria-label="清空搜索" @click="filters.q = ''; applyFilters()"><i class="fas fa-xmark"></i></button>
        </label>
      </div>

      <form v-if="showFilters" class="advanced-filters" @submit.prevent="applyFilters">
        <label>
          <span>平台</span>
          <select v-model="filters.platform">
            <option value="">全部平台</option>
            <option v-for="platform in platforms" :key="platform" :value="platform">{{ platformName(platform) }}</option>
          </select>
        </label>
        <label>
          <span>酒旅相关性</span>
          <select v-model="filters.hospitality_relevance">
            <option value="">全部相关性</option>
            <option value="relevant">高度相关</option>
            <option value="possibly_relevant">可能相关</option>
            <option value="irrelevant">不相关</option>
          </select>
        </label>
        <label>
          <span>数据质量</span>
          <select v-model="filters.data_quality">
            <option value="">全部质量</option>
            <option value="complete">数据完整</option>
            <option value="partial">部分缺失</option>
          </select>
        </label>
        <div class="advanced-filter-actions">
          <button v-if="isFiltered" type="button" class="secondary-button" @click="clearFilters">重置</button>
          <button type="submit" class="primary-button" :disabled="store.loading">
            <i :class="['fas', store.loading ? 'fa-circle-notch fa-spin' : 'fa-check']"></i>应用筛选
          </button>
        </div>
      </form>

      <div v-if="store.loading && !store.overview" class="event-skeletons">
        <div v-for="index in 5" :key="index" class="event-skeleton skeleton"></div>
      </div>

      <div v-else-if="!store.overview?.has_data" class="honest-empty-state">
        <div class="empty-state-icon"><i class="fas fa-database"></i></div>
        <h3>等待首次真实采集</h3>
        <p>Collector 完成生产采集后，聚合事件会出现在这里。系统不会使用演示或伪造热点填充空白区域。</p>
        <RouterLink to="/sources">检查数据源状态 <i class="fas fa-arrow-right"></i></RouterLink>
      </div>

      <div v-else-if="store.events.items.length === 0" class="honest-empty-state honest-empty-state--compact">
        <div class="empty-state-icon"><i class="fas fa-filter-circle-xmark"></i></div>
        <h3>当前条件下没有事件</h3>
        <p>可以调整平台、趋势阶段或酒旅相关性筛选。</p>
        <button type="button" @click="clearFilters">清除全部筛选</button>
      </div>

      <div v-else :class="['events-list', `events-list--${displayMode}`, { 'events-list--refreshing': store.loading }]">
        <button
          v-for="(event, index) in store.events.items"
          :key="event.event_id"
          type="button"
          class="event-row"
          @click="store.openEvent(event.event_id)"
        >
          <span class="event-rank">{{ String(filters.offset + index + 1).padStart(2, '0') }}</span>
          <span class="event-main">
            <span class="event-badges">
              <span :class="['lifecycle-badge', `lifecycle-badge--${lifecycleTone(event.lifecycle_state)}`]">
                <i :class="['fas', lifecycleIcon(event.lifecycle_state)]"></i>{{ lifecycleLabel(event.lifecycle_state) }}
              </span>
              <span :class="['quality-badge', event.data_quality === 'complete' ? 'quality-badge--good' : 'quality-badge--warn']">
                {{ event.data_quality === 'complete' ? '完整' : '部分缺失' }}
              </span>
              <span v-for="platform in event.platforms" :key="platform" class="platform-badge">{{ platformName(platform) }}</span>
            </span>
            <strong>{{ event.canonical_title }}</strong>
            <span v-if="event.classification?.summary" class="event-summary">{{ event.classification.summary }}</span>
            <span v-else class="event-summary event-summary--empty">AI 摘要未生成，不补写推测内容。</span>
            <span class="event-footnote">
              <span>{{ formatTimestamp(event.last_seen_at) }}</span>
              <span>{{ event.observation_count }} 条原始观测</span>
              <span>{{ event.platform_count }} 个平台</span>
            </span>
          </span>
          <span class="event-signal">
            <span>趋势分</span>
            <strong>{{ formatNumber(event.trend_score) }}</strong>
            <small :class="trendDirectionClass(event.velocity)"><i :class="['fas', trendDirectionIcon(event.velocity)]"></i>{{ formatSigned(event.velocity) }}</small>
          </span>
          <span class="event-relevance">
            <span>酒旅研判</span>
            <strong>{{ relevanceLabel(event.classification?.hospitality_relevance) }}</strong>
            <small>{{ formatPercent(event.classification?.confidence) }} 置信度</small>
          </span>
          <span class="event-open"><i class="fas fa-chevron-right"></i></span>
        </button>
      </div>

      <footer v-if="store.events.total > filters.limit" class="pagination-bar">
        <button type="button" :disabled="filters.offset === 0 || store.loading" @click="page(-1)"><i class="fas fa-arrow-left"></i>上一页</button>
        <span>{{ filters.offset + 1 }}–{{ Math.min(filters.offset + filters.limit, store.events.total) }} / {{ store.events.total }}</span>
        <button type="button" :disabled="filters.offset + filters.limit >= store.events.total || store.loading" @click="page(1)">下一页<i class="fas fa-arrow-right"></i></button>
      </footer>
    </section>

    <EventDetailDrawer
      v-if="store.detailLoading || store.selectedEvent"
      :event="store.selectedEvent"
      :loading="store.detailLoading"
      @close="store.closeEvent()"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'

import EventDetailDrawer from '../components/intelligence/EventDetailDrawer.vue'
import PlatformHealthStrip from '../components/intelligence/PlatformHealthStrip.vue'
import { useAppStore } from '../stores/app'
import { useHotspotDashboardStore } from '../stores/hotspotDashboard'
import {
  formatTimestamp,
  lifecycleLabel,
  lifecycleTone,
  platformName,
  relevanceLabel,
  summarizePlatformHealth,
} from '../utils/hotspotDashboard'

const store = useHotspotDashboardStore()
const appStore = useAppStore()
const platforms = ['douyin', 'weibo', 'bilibili', 'xiaohongshu']
const displayMode = ref('dense')
const showFilters = ref(false)
const filters = reactive({
  q: '',
  platform: '',
  lifecycle: '',
  hospitality_relevance: '',
  data_quality: '',
  limit: 20,
  offset: 0,
})

const quickLifecycleOptions = [
  { value: '', label: '全部事件' },
  { value: 'emerging', label: '新出现' },
  { value: 'rising', label: '快速上升' },
  { value: 'peaking', label: '正在峰值' },
  { value: 'recurring', label: '再次复燃' },
]

const platformCards = computed(() => store.overview?.platforms || platforms.map(platform => ({
  platform,
  status: 'unavailable',
  data_age_minutes: null,
  winning_provider_id: null,
})))
const health = computed(() => summarizePlatformHealth(platformCards.value))
const overviewStatusText = computed(() => {
  if (!store.overview?.trend_run) return '尚未运行'
  return store.overview.trend_run.status === 'partial' ? '部分数据' : '运行完整'
})
const overviewStatusTone = computed(() => store.overview?.trend_run?.status === 'partial' ? 'run-warning' : store.overview?.trend_run ? 'run-good' : 'run-muted')
const platformHealthSummary = computed(() => {
  if (health.value.attention) return `${health.value.attention} 个需关注`
  if (health.value.unavailable) return `${health.value.unavailable} 个尚无数据`
  return '采集状态正常'
})
const hasAdvancedFilters = computed(() => Boolean(filters.platform || filters.hospitality_relevance || filters.data_quality))
const isFiltered = computed(() => Boolean(filters.q || filters.platform || filters.lifecycle || filters.hospitality_relevance || filters.data_quality))

function applyFilters() {
  filters.offset = 0
  store.refresh(filters)
}

function setLifecycle(value) {
  filters.lifecycle = value
  applyFilters()
}

function selectPlatform(value) {
  filters.platform = filters.platform === value ? '' : value
  applyFilters()
}

function clearFilters() {
  Object.assign(filters, { q: '', platform: '', lifecycle: '', hospitality_relevance: '', data_quality: '', offset: 0 })
  store.refresh(filters)
}

function page(direction) {
  filters.offset = Math.max(0, filters.offset + direction * filters.limit)
  store.refresh(filters)
}

function formatNumber(value) {
  return value === null || value === undefined ? '—' : Number(value).toFixed(1)
}

function formatSigned(value) {
  if (value === null || value === undefined) return '无速度值'
  const number = Number(value)
  return `${number > 0 ? '+' : ''}${number.toFixed(2)}`
}

function formatPercent(value) {
  return value === null || value === undefined ? '无' : `${Math.round(Number(value) * 100)}%`
}

function lifecycleIcon(value) {
  return {
    emerging: 'fa-seedling',
    rising: 'fa-arrow-trend-up',
    peaking: 'fa-bolt',
    declining: 'fa-arrow-trend-down',
    dormant: 'fa-minus',
    recurring: 'fa-rotate',
  }[value] || 'fa-circle'
}

function trendDirectionClass(value) {
  if (Number(value) > 0) return 'signal-positive'
  if (Number(value) < 0) return 'signal-negative'
  return 'signal-flat'
}

function trendDirectionIcon(value) {
  if (Number(value) > 0) return 'fa-arrow-up'
  if (Number(value) < 0) return 'fa-arrow-down'
  return 'fa-minus'
}

onMounted(() => store.refresh(filters))
watch(() => appStore.refreshTrigger, () => store.refresh(filters))
</script>

<style scoped>
.intelligence-page { display: grid; gap: 16px; padding-bottom: 28px; }
.truth-alert { display: flex; align-items: flex-start; gap: 12px; padding: 13px 15px; border: 1px solid; border-radius: 13px; font-size: 12px; }
.truth-alert > i { margin-top: 2px; }.truth-alert strong { color: var(--text-strong); }.truth-alert p { margin: 3px 0 0; color: var(--text-muted); line-height: 1.5; }
.truth-alert--danger { color: #f87171; border-color: rgb(239 68 68 / 20%); background: rgb(239 68 68 / 8%); }
.truth-alert--warning { color: #fbbf24; border-color: rgb(245 158 11 / 20%); background: rgb(245 158 11 / 7%); }
.overview-panel { display: flex; align-items: flex-end; justify-content: space-between; gap: 32px; padding: 30px 32px; overflow: hidden; border: 1px solid var(--line-subtle); border-radius: 18px; background: var(--surface-hero); box-shadow: var(--shadow-panel); }
.overview-copy { max-width: 740px; }.overview-kicker { display: flex; flex-wrap: wrap; gap: 9px 14px; color: var(--text-subtle); font-size: 10px; font-weight: 650; letter-spacing: .08em; text-transform: uppercase; }
.live-indicator { color: var(--accent-strong); }.live-indicator > span { display: inline-block; width: 6px; height: 6px; margin-right: 7px; border-radius: 50%; background: var(--accent-primary); box-shadow: 0 0 0 4px var(--accent-soft); }
.overview-copy h1 { max-width: 650px; margin: 13px 0 0; color: var(--text-strong); font-size: clamp(24px, 3vw, 38px); font-weight: 720; letter-spacing: -.035em; line-height: 1.16; }
.overview-copy p { max-width: 650px; margin: 13px 0 0; color: var(--text-muted); font-size: 13px; line-height: 1.75; }
.overview-run { flex: 0 0 160px; padding-left: 22px; border-left: 1px solid var(--line-subtle); }.overview-run span,.overview-run small { display: block; color: var(--text-subtle); font-size: 10px; }.overview-run strong { display: block; margin: 8px 0 5px; font-size: 17px; }.run-good { color: #22c55e; }.run-warning { color: #f59e0b; }.run-muted { color: var(--text-muted); }
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }.metric-card { display: flex; align-items: center; gap: 14px; min-width: 0; padding: 17px 18px; border: 1px solid var(--line-subtle); border-radius: 15px; background: var(--surface-panel); box-shadow: var(--shadow-panel); }.metric-icon { display: grid; flex: 0 0 auto; width: 38px; height: 38px; place-items: center; border-radius: 11px; font-size: 13px; }.metric-icon--gold { color: #fbbf24; background: rgb(251 191 36 / 10%); }.metric-icon--green { color: #34d399; background: rgb(52 211 153 / 10%); }.metric-icon--blue { color: #60a5fa; background: rgb(96 165 250 / 10%); }.metric-icon--violet { color: #a78bfa; background: rgb(167 139 250 / 10%); }
.metric-card > div:last-child { min-width: 0; }.metric-card p,.metric-card span { display: block; margin: 0; color: var(--text-subtle); font-size: 10px; }.metric-card strong { display: block; margin: 3px 0 2px; color: var(--text-strong); font-size: 21px; line-height: 1.15; }.metric-card strong small { color: var(--text-muted); font-size: 12px; }.metric-card .metric-card__time { overflow: hidden; font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.workspace-panel { overflow: hidden; border: 1px solid var(--line-subtle); border-radius: 18px; background: var(--surface-panel); box-shadow: var(--shadow-panel); }.workspace-header { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; padding: 22px 24px 18px; border-bottom: 1px solid var(--line-subtle); }.section-kicker { margin: 0 0 5px; color: var(--accent-strong); font-size: 9px; font-weight: 750; letter-spacing: .16em; }.workspace-header h2 { margin: 0; color: var(--text-strong); font-size: 18px; }.workspace-header > div:first-child > span { display: block; margin-top: 6px; color: var(--text-muted); font-size: 11px; }
.view-actions { display: flex; gap: 5px; }.view-actions button { display: grid; height: 34px; min-width: 34px; place-items: center; padding: 0 9px; color: var(--text-muted); font-size: 12px; border: 1px solid transparent; border-radius: 9px; background: var(--surface-soft); }.view-actions button:hover,.view-actions button.active { color: var(--text-strong); border-color: var(--line-strong); }.view-actions .filter-toggle { display: flex; gap: 7px; margin-left: 5px; }
.quick-filter-row { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 12px 24px; border-bottom: 1px solid var(--line-subtle); background: var(--surface-soft); }.quick-filters { display: flex; gap: 4px; overflow-x: auto; }.quick-filters button { flex: 0 0 auto; padding: 7px 10px; color: var(--text-muted); font-size: 11px; border-radius: 8px; }.quick-filters button:hover,.quick-filters button.active { color: var(--text-strong); background: var(--surface-hover); box-shadow: inset 0 0 0 1px var(--line-subtle); }
.event-search { display: flex; align-items: center; gap: 8px; width: min(280px, 100%); padding: 7px 10px; color: var(--text-subtle); border: 1px solid var(--line-subtle); border-radius: 9px; background: var(--surface-panel); }.event-search input { min-width: 0; flex: 1; color: var(--text-default); font-size: 11px; outline: 0; background: transparent; }.event-search input::placeholder { color: var(--text-subtle); }.event-search button { color: var(--text-subtle); }
.advanced-filters { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)) auto; gap: 12px; align-items: end; padding: 15px 24px; border-bottom: 1px solid var(--line-subtle); background: var(--surface-soft); }.advanced-filters label span { display: block; margin-bottom: 6px; color: var(--text-subtle); font-size: 10px; }.advanced-filters select { width: 100%; padding: 8px 10px; color: var(--text-default); font-size: 11px; border: 1px solid var(--line-subtle); border-radius: 9px; outline: 0; background: var(--surface-panel); }.advanced-filter-actions { display: flex; gap: 7px; }.primary-button,.secondary-button { height: 34px; padding: 0 13px; font-size: 11px; border-radius: 9px; }.primary-button { display: flex; align-items: center; gap: 7px; color: var(--accent-button-text); background: var(--accent-primary); }.secondary-button { color: var(--text-muted); border: 1px solid var(--line-subtle); background: var(--surface-panel); }
.events-list { transition: opacity 150ms ease; }.events-list--refreshing { opacity: .55; pointer-events: none; }.event-row { display: grid; grid-template-columns: 38px minmax(0, 1fr) 100px 124px 18px; gap: 16px; align-items: center; width: 100%; padding: 17px 24px; text-align: left; border-bottom: 1px solid var(--line-subtle); transition: background-color 150ms ease; }.event-row:hover { background: var(--surface-hover); }.event-row:last-child { border-bottom: 0; }.event-rank { align-self: start; padding-top: 3px; color: var(--text-subtle); font-size: 11px; font-variant-numeric: tabular-nums; }.event-main { display: block; min-width: 0; }.event-badges { display: flex; flex-wrap: wrap; gap: 5px; }.lifecycle-badge,.quality-badge,.platform-badge { display: inline-flex; align-items: center; gap: 5px; padding: 4px 6px; color: var(--text-muted); font-size: 9px; border-radius: 6px; background: var(--surface-soft); }.lifecycle-badge--cyan { color: #22d3ee; background: rgb(34 211 238 / 9%); }.lifecycle-badge--emerald { color: #34d399; background: rgb(52 211 153 / 9%); }.lifecycle-badge--amber { color: #fbbf24; background: rgb(251 191 36 / 9%); }.lifecycle-badge--violet { color: #a78bfa; background: rgb(167 139 250 / 9%); }.quality-badge--good { color: #22c55e; }.quality-badge--warn { color: #f59e0b; }.event-main > strong { display: block; margin-top: 9px; overflow: hidden; color: var(--text-strong); font-size: 13px; font-weight: 630; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }.event-summary { display: -webkit-box; margin-top: 5px; overflow: hidden; color: var(--text-muted); font-size: 11px; line-height: 1.55; -webkit-box-orient: vertical; -webkit-line-clamp: 1; }.event-summary--empty { color: var(--text-subtle); }.event-footnote { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-top: 8px; color: var(--text-subtle); font-size: 9px; }.event-signal,.event-relevance { display: flex; flex-direction: column; align-items: flex-start; }.event-signal > span,.event-relevance > span { color: var(--text-subtle); font-size: 9px; }.event-signal > strong { margin-top: 4px; color: var(--text-strong); font-size: 19px; }.event-signal small,.event-relevance small { margin-top: 2px; font-size: 9px; }.event-signal small i { margin-right: 4px; }.signal-positive { color: #22c55e; }.signal-negative { color: #f87171; }.signal-flat { color: var(--text-subtle); }.event-relevance > strong { margin-top: 6px; color: var(--accent-strong); font-size: 11px; }.event-relevance small { color: var(--text-subtle); }.event-open { color: var(--text-subtle); font-size: 10px; }
.events-list--cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0; }.events-list--cards .event-row { grid-template-columns: 28px minmax(0, 1fr) 80px; grid-template-areas: 'rank main open' 'rank signal relevance'; gap: 13px; align-items: start; border-right: 1px solid var(--line-subtle); }.events-list--cards .event-rank { grid-area: rank; }.events-list--cards .event-main { grid-area: main; }.events-list--cards .event-signal { grid-area: signal; padding-top: 5px; }.events-list--cards .event-relevance { grid-area: relevance; padding-top: 5px; }.events-list--cards .event-open { grid-area: open; justify-self: end; }.events-list--cards .event-main > strong { white-space: normal; }.events-list--cards .event-summary { -webkit-line-clamp: 2; }
.event-skeletons { padding: 18px 24px; }.event-skeleton { height: 92px; margin-bottom: 8px; border-radius: 12px; }.honest-empty-state { display: flex; min-height: 340px; flex-direction: column; align-items: center; justify-content: center; padding: 40px 20px; text-align: center; }.honest-empty-state--compact { min-height: 260px; }.empty-state-icon { display: grid; width: 48px; height: 48px; place-items: center; color: var(--text-subtle); border: 1px solid var(--line-subtle); border-radius: 15px; background: var(--surface-soft); }.honest-empty-state h3 { margin: 16px 0 0; color: var(--text-strong); font-size: 15px; }.honest-empty-state p { max-width: 480px; margin: 8px 0 0; color: var(--text-muted); font-size: 11px; line-height: 1.7; }.honest-empty-state a,.honest-empty-state button { margin-top: 18px; color: var(--accent-strong); font-size: 11px; }.honest-empty-state a i { margin-left: 5px; }
.pagination-bar { display: flex; align-items: center; justify-content: space-between; padding: 13px 24px; color: var(--text-subtle); font-size: 10px; border-top: 1px solid var(--line-subtle); background: var(--surface-soft); }.pagination-bar button { display: flex; align-items: center; gap: 7px; color: var(--text-muted); }.pagination-bar button:hover { color: var(--text-strong); }.pagination-bar button:disabled { opacity: .3; }
@media (max-width: 1100px) { .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.event-row { grid-template-columns: 32px minmax(0, 1fr) 82px 110px 14px; gap: 12px; }.events-list--cards { grid-template-columns: 1fr; } }
@media (max-width: 760px) { .overview-panel { align-items: flex-start; padding: 24px 20px; }.overview-run { display: none; }.metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.metric-card { padding: 14px; }.metric-icon { width: 34px; height: 34px; }.workspace-header { align-items: flex-start; padding: 18px 16px 14px; }.workspace-header > div:first-child > span { max-width: 220px; }.view-actions > button:not(.filter-toggle) { display: none; }.quick-filter-row { flex-direction: column-reverse; align-items: stretch; padding: 10px 14px; }.event-search { width: 100%; }.quick-filters { margin: 0 -2px; }.advanced-filters { grid-template-columns: 1fr; padding: 14px; }.event-row,.events-list--cards .event-row { grid-template-columns: 24px minmax(0, 1fr) 14px; grid-template-areas: 'rank main open' 'rank signal relevance'; gap: 11px; padding: 15px 14px; border-right: 0; }.event-rank { grid-area: rank; }.event-main { grid-area: main; }.event-signal { grid-area: signal; padding-top: 4px; }.event-relevance { grid-area: relevance; padding-top: 4px; }.event-open { grid-area: open; }.event-main > strong { white-space: normal; }.event-summary { -webkit-line-clamp: 2; }.event-footnote span:first-child { display: none; } }
@media (max-width: 470px) { .metric-grid { grid-template-columns: 1fr; }.metric-card { min-height: 72px; }.overview-copy h1 { font-size: 25px; }.overview-copy p { font-size: 12px; }.workspace-header > div:first-child > span { display: none; }.filter-toggle span { display: none; } }
</style>
