<template>
  <Teleport to="body">
    <div class="drawer-layer" role="presentation" @click.self="$emit('close')">
      <aside class="event-drawer" role="dialog" aria-modal="true" aria-labelledby="event-drawer-title">
        <div v-if="loading" class="drawer-loading">
          <i class="fas fa-circle-notch fa-spin"></i>
          <span>正在读取原始证据链</span>
        </div>

        <template v-else-if="event">
          <header class="drawer-header">
            <div class="drawer-header__copy">
              <div class="drawer-kicker">
                <span :class="['lifecycle-pill', `lifecycle-pill--${lifecycleTone(event.lifecycle_state)}`]">
                  {{ lifecycleLabel(event.lifecycle_state) }}
                </span>
                <span>趋势分 {{ formatNumber(event.trend_score) }}</span>
                <span>更新于 {{ formatTimestamp(event.evaluated_at) }}</span>
              </div>
              <h2 id="event-drawer-title">{{ event.canonical_title }}</h2>
            </div>
            <button type="button" class="icon-button" aria-label="关闭事件详情" @click="$emit('close')">
              <i class="fas fa-xmark"></i>
            </button>
          </header>

          <nav class="drawer-tabs" aria-label="事件详情栏目">
            <button
              v-for="tab in tabs"
              :key="tab.value"
              type="button"
              :class="{ active: activeTab === tab.value }"
              @click="activeTab = tab.value"
            >
              {{ tab.label }}
              <span v-if="tab.value === 'evidence'">{{ event.evidence?.length || 0 }}</span>
            </button>
          </nav>

          <div class="drawer-content">
            <template v-if="activeTab === 'brief'">
              <section class="brief-grid">
                <article class="brief-card brief-card--wide">
                  <p class="eyebrow">AI 研判摘要</p>
                  <p v-if="event.classification?.summary" class="brief-copy">{{ event.classification.summary }}</p>
                  <p v-else class="empty-copy">该事件没有可用的 AI 摘要，系统不会补写推测内容。</p>
                  <p v-if="event.classification?.rationale" class="rationale">
                    <span>判定依据</span>{{ event.classification.rationale }}
                  </p>
                </article>

                <article class="brief-card">
                  <p class="eyebrow">酒旅相关性</p>
                  <p class="relevance-value">{{ relevanceLabel(event.classification?.hospitality_relevance) }}</p>
                  <dl class="metric-list">
                    <div><dt>置信度</dt><dd>{{ formatPercent(event.classification?.confidence) }}</dd></div>
                    <div><dt>相关评分</dt><dd>{{ formatNumber(event.classification?.hospitality_score) }}</dd></div>
                    <div><dt>主题分类</dt><dd>{{ event.classification?.topic_category || '未分类' }}</dd></div>
                  </dl>
                </article>
              </section>

              <section class="signal-section">
                <div class="section-heading">
                  <div><p class="eyebrow">趋势信号</p><h3>传播状态与数据质量</h3></div>
                  <span :class="['quality-pill', event.data_quality === 'complete' ? 'quality-pill--good' : 'quality-pill--warn']">
                    {{ event.data_quality === 'complete' ? '数据完整' : '数据部分缺失' }}
                  </span>
                </div>
                <dl class="signal-metrics">
                  <div><dt>覆盖平台</dt><dd>{{ event.platform_count }}</dd></div>
                  <div><dt>原始观测</dt><dd>{{ event.observation_count }}</dd></div>
                  <div><dt>传播速度</dt><dd>{{ formatSigned(event.velocity) }}</dd></div>
                  <div><dt>加速度</dt><dd>{{ formatSigned(event.acceleration) }}</dd></div>
                  <div><dt>完整度</dt><dd>{{ formatPercent(event.data_completeness) }}</dd></div>
                </dl>
                <div class="tag-row">
                  <span v-for="platform in event.platforms" :key="platform" class="soft-tag">{{ platformName(platform) }}</span>
                  <span v-for="tag in event.classification?.tags || []" :key="tag" class="soft-tag soft-tag--accent">{{ tag }}</span>
                </div>
              </section>
            </template>

            <section v-else-if="activeTab === 'evidence'" class="evidence-section">
              <div class="section-heading">
                <div>
                  <p class="eyebrow">原始证据</p>
                  <h3>可追溯热点记录</h3>
                </div>
                <p>每条记录均来自持久化的 RawHotItem</p>
              </div>

              <div class="evidence-list">
                <article v-for="item in event.evidence" :key="item.raw_item_id" class="evidence-item">
                  <div class="evidence-item__rail">
                    <span :class="['status-dot', item.freshness === 'fresh' ? 'status-dot--fresh' : 'status-dot--stale']"></span>
                    <span class="evidence-line"></span>
                  </div>
                  <div class="evidence-item__body">
                    <div class="evidence-meta">
                      <span>{{ platformName(item.platform) }}</span>
                      <span>{{ item.provider_id }}</span>
                      <span>榜单 #{{ item.rank ?? '-' }}</span>
                      <span :class="item.freshness === 'fresh' ? 'fresh-text' : 'stale-text'">
                        {{ item.freshness === 'fresh' ? '实时采集' : '陈旧数据' }}
                      </span>
                    </div>
                    <h4>{{ item.title }}</h4>
                    <p>观测于 {{ formatTimestamp(item.observed_at) }} · Raw ID {{ item.raw_item_id }}</p>
                    <div class="evidence-actions">
                      <a v-if="item.source_url" :href="item.source_url" target="_blank" rel="noopener noreferrer">查看原平台 <i class="fas fa-arrow-up-right-from-square"></i></a>
                      <a v-if="item.raw_item_url" :href="item.raw_item_url" target="_blank" rel="noopener noreferrer">读取原始记录</a>
                    </div>
                  </div>
                </article>
                <div v-if="!event.evidence?.length" class="empty-evidence">当前事件没有可读取的原始证据记录。</div>
              </div>
            </section>

            <section v-else-if="activeTab === 'review'" class="review-section">
              <div class="section-heading">
                <div>
                  <p class="eyebrow">人工研判</p>
                  <h3>标记分类与业务判断</h3>
                </div>
                <span v-if="event.annotation" class="revision-pill">版本 {{ event.annotation.revision }}</span>
              </div>
              <p class="section-note">人工结论单独留痕，不覆盖 AI 分类和原始热点；每次保存都会生成新的审计版本。</p>

              <form class="review-form" @submit.prevent="saveReview">
                <div class="form-grid">
                  <label>
                    <span>审核状态</span>
                    <select v-model="reviewDraft.review_status">
                      <option value="reviewed">已确认</option>
                      <option value="watch">持续观察</option>
                      <option value="ignored">忽略</option>
                    </select>
                  </label>
                  <label>
                    <span>人工分类</span>
                    <input v-model="reviewDraft.topic_category" maxlength="80" placeholder="例如：酒店营销、出行风险" />
                  </label>
                  <label>
                    <span>酒旅相关性</span>
                    <select v-model="reviewDraft.hospitality_relevance">
                      <option value="">未判断</option>
                      <option value="relevant">直接相关</option>
                      <option value="possibly_relevant">可能相关</option>
                      <option value="irrelevant">不相关</option>
                    </select>
                  </label>
                  <label>
                    <span>决策通道</span>
                    <select v-model="reviewDraft.decision_lane">
                      <option value="">未选择</option>
                      <option value="opportunity">经营机会</option>
                      <option value="context_signal">环境信号</option>
                      <option value="risk_watch">风险观察</option>
                      <option value="reference_material">内容素材</option>
                      <option value="background">背景资料</option>
                    </select>
                  </label>
                </div>
                <label class="form-field--wide">
                  <span>标签</span>
                  <input v-model="reviewDraft.tags" placeholder="用逗号分隔，例如：暑期、亲子游、价格" />
                </label>
                <label class="form-field--wide">
                  <span>人工摘要</span>
                  <textarea v-model="reviewDraft.summary_override" maxlength="2000" rows="4" placeholder="可选：写入你确认后的事件摘要"></textarea>
                </label>
                <label class="form-field--wide">
                  <span>内部备注</span>
                  <textarea v-model="reviewDraft.notes" maxlength="4000" rows="4" placeholder="记录判断依据、待办或跟进人员"></textarea>
                </label>
                <div v-if="actionError" class="action-error">{{ actionError }}</div>
                <div class="form-actions">
                  <span v-if="event.annotation">上次由 {{ event.annotation.updated_by }} 于 {{ formatTimestamp(event.annotation.created_at) }} 保存</span>
                  <button type="submit" class="primary-action" :disabled="annotationSaving">
                    <i :class="['fas', annotationSaving ? 'fa-circle-notch fa-spin' : 'fa-floppy-disk']"></i>
                    {{ annotationSaving ? '正在保存' : '保存人工标记' }}
                  </button>
                </div>
              </form>
            </section>

            <section v-else class="knowledge-section">
              <div class="knowledge-status-card">
                <div>
                  <p class="eyebrow">知识互通</p>
                  <h3>{{ knowledgeConfigurationText(event.knowledge_integration) }}</h3>
                  <p>仅手动同步已保存的人工标记；检索会在当前 WeKnora 知识库中寻找关联资料。</p>
                </div>
                <span :class="['connection-dot', { 'connection-dot--ready': event.knowledge_integration?.configured }]"></span>
              </div>

              <div v-if="event.knowledge_sync" class="sync-record">
                <div><span>最近同步</span><strong>{{ event.knowledge_sync.status === 'success' ? '成功' : '失败' }}</strong></div>
                <div><span>操作</span><strong>{{ event.knowledge_sync.operation === 'update' ? '更新知识' : '新建知识' }}</strong></div>
                <div><span>时间</span><strong>{{ formatTimestamp(event.knowledge_sync.finished_at) }}</strong></div>
              </div>

              <div class="knowledge-actions">
                <button
                  type="button"
                  class="primary-action"
                  :disabled="knowledgeLoading || !event.annotation || !event.knowledge_integration?.configured"
                  @click="$emit('sync-knowledge')"
                >
                  <i :class="['fas', knowledgeLoading ? 'fa-circle-notch fa-spin' : 'fa-cloud-arrow-up']"></i>
                  同步当前人工版本
                </button>
                <span v-if="!event.annotation">请先在“人工标记”中保存判断。</span>
              </div>

              <form class="knowledge-search" @submit.prevent="$emit('search-knowledge', searchQuery)">
                <label for="knowledge-query">关联知识检索</label>
                <div>
                  <input id="knowledge-query" v-model="searchQuery" maxlength="300" :placeholder="event.canonical_title" />
                  <button type="submit" :disabled="knowledgeLoading || !event.knowledge_integration?.configured">
                    <i class="fas fa-magnifying-glass"></i>检索
                  </button>
                </div>
                <small>留空时使用事件标题、人工标签和分类组合检索。</small>
              </form>

              <div v-if="actionError" class="action-error">{{ actionError }}</div>
              <div v-if="knowledgeQuery" class="search-caption">当前检索：{{ knowledgeQuery }}</div>
              <div class="knowledge-results">
                <article v-for="hit in knowledgeHits" :key="`${hit.knowledge_id}-${hit.chunk_id}`" class="knowledge-hit">
                  <div>
                    <strong>{{ hit.knowledge_title || '未命名知识' }}</strong>
                    <span v-if="hit.score !== null && hit.score !== undefined">相关度 {{ Number(hit.score).toFixed(3) }}</span>
                  </div>
                  <p>{{ hit.content }}</p>
                </article>
                <div v-if="knowledgeQuery && !knowledgeHits.length && !knowledgeLoading" class="empty-evidence">没有检索到关联知识。</div>
              </div>
            </section>
          </div>
        </template>
      </aside>
    </div>
  </Teleport>
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  formatTimestamp,
  lifecycleLabel,
  lifecycleTone,
  platformName,
  relevanceLabel,
} from '../../utils/hotspotDashboard'
import {
  annotationDraft,
  annotationPayload,
  knowledgeConfigurationText,
} from '../../utils/hotspotAnnotations'

const props = defineProps({
  event: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  annotationSaving: { type: Boolean, default: false },
  knowledgeLoading: { type: Boolean, default: false },
  knowledgeHits: { type: Array, default: () => [] },
  knowledgeQuery: { type: String, default: '' },
  actionError: { type: String, default: '' },
})

const emit = defineEmits(['close', 'save-annotation', 'sync-knowledge', 'search-knowledge'])
const activeTab = ref('brief')
const reviewDraft = reactive(annotationDraft(props.event))
const searchQuery = ref('')
const tabs = [
  { value: 'brief', label: '研判摘要' },
  { value: 'evidence', label: '原始证据' },
  { value: 'review', label: '人工标记' },
  { value: 'knowledge', label: '知识库' },
]

function saveReview() {
  emit('save-annotation', annotationPayload(reviewDraft))
}

function formatNumber(value) {
  return value === null || value === undefined ? '未提供' : Number(value).toFixed(2)
}

function formatSigned(value) {
  if (value === null || value === undefined) return '未提供'
  const number = Number(value)
  return `${number > 0 ? '+' : ''}${number.toFixed(2)}`
}

function formatPercent(value) {
  return value === null || value === undefined ? '未提供' : `${Math.round(Number(value) * 100)}%`
}

function handleKeydown(event) {
  if (event.key === 'Escape') emit('close')
}

watch(
  () => props.event,
  event => Object.assign(reviewDraft, annotationDraft(event)),
  { immediate: true },
)

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
  document.body.classList.add('drawer-open')
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
  document.body.classList.remove('drawer-open')
})
</script>

<style scoped>
.drawer-layer {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: flex;
  justify-content: flex-end;
  background: rgb(3 8 14 / 58%);
  backdrop-filter: blur(5px);
}

.event-drawer {
  width: min(760px, 100%);
  height: 100%;
  overflow-y: auto;
  color: var(--text-default);
  background: var(--surface-drawer);
  border-left: 1px solid var(--line-strong);
  box-shadow: -28px 0 70px rgb(0 0 0 / 28%);
  animation: drawer-in 220ms cubic-bezier(.2,.8,.2,1);
}

.drawer-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  height: 100%;
  color: var(--text-muted);
}

.drawer-header {
  position: sticky;
  top: 0;
  z-index: 2;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 26px 28px 20px;
  background: color-mix(in srgb, var(--surface-drawer) 92%, transparent);
  border-bottom: 1px solid var(--line-subtle);
  backdrop-filter: blur(16px);
}
.drawer-header__copy { min-width: 0; }
.drawer-header h2 { margin: 12px 0 0; color: var(--text-strong); font-size: 23px; line-height: 1.35; }
.drawer-kicker { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; color: var(--text-muted); font-size: 11px; }

.icon-button {
  display: grid;
  flex: 0 0 auto;
  width: 36px;
  height: 36px;
  place-items: center;
  color: var(--text-muted);
  border: 1px solid var(--line-subtle);
  border-radius: 10px;
  background: var(--surface-soft);
}
.icon-button:hover { color: var(--text-strong); border-color: var(--line-strong); }

.drawer-tabs { display: flex; gap: 24px; padding: 0 28px; border-bottom: 1px solid var(--line-subtle); }
.drawer-tabs button { padding: 16px 0 13px; color: var(--text-muted); font-size: 13px; border-bottom: 2px solid transparent; }
.drawer-tabs button.active { color: var(--text-strong); border-bottom-color: var(--accent-primary); }
.drawer-tabs span { margin-left: 5px; color: var(--text-subtle); }
.drawer-content { padding: 24px 28px 40px; }

.brief-grid { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(220px, .8fr); gap: 14px; }
.brief-card, .signal-section { padding: 20px; border: 1px solid var(--line-subtle); border-radius: 15px; background: var(--surface-panel); }
.eyebrow { margin: 0; color: var(--text-subtle); font-size: 10px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
.brief-copy { margin: 12px 0 0; color: var(--text-default); font-size: 14px; line-height: 1.8; }
.empty-copy { margin: 12px 0 0; color: var(--text-muted); font-size: 13px; line-height: 1.7; }
.rationale { margin: 16px 0 0; padding-top: 14px; color: var(--text-muted); font-size: 12px; line-height: 1.7; border-top: 1px solid var(--line-subtle); }
.rationale span { display: block; margin-bottom: 4px; color: var(--text-subtle); font-weight: 650; }
.relevance-value { margin: 12px 0 16px; color: var(--accent-strong); font-size: 20px; font-weight: 700; }
.metric-list { display: grid; gap: 10px; margin: 0; }
.metric-list div { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; }
.metric-list dt { color: var(--text-muted); }
.metric-list dd { margin: 0; color: var(--text-default); text-align: right; }

.signal-section { margin-top: 14px; }
.section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.section-heading h3 { margin: 5px 0 0; color: var(--text-strong); font-size: 15px; }
.section-heading > p { margin: 0; color: var(--text-subtle); font-size: 11px; }
.signal-metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; margin: 18px 0 0; }
.signal-metrics div { padding: 12px; border-radius: 10px; background: var(--surface-soft); }
.signal-metrics dt { color: var(--text-subtle); font-size: 10px; }
.signal-metrics dd { margin: 5px 0 0; color: var(--text-strong); font-size: 15px; font-weight: 700; }
.tag-row { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 16px; }
.soft-tag, .quality-pill, .lifecycle-pill { padding: 5px 8px; color: var(--text-muted); font-size: 10px; border-radius: 7px; background: var(--surface-soft); }
.soft-tag--accent { color: var(--accent-strong); background: var(--accent-soft); }
.quality-pill--good { color: #22c55e; background: rgb(34 197 94 / 10%); }
.quality-pill--warn { color: #f59e0b; background: rgb(245 158 11 / 10%); }
.lifecycle-pill--cyan { color: #22d3ee; background: rgb(34 211 238 / 10%); }
.lifecycle-pill--emerald { color: #34d399; background: rgb(52 211 153 / 10%); }
.lifecycle-pill--amber { color: #fbbf24; background: rgb(251 191 36 / 10%); }
.lifecycle-pill--violet { color: #a78bfa; background: rgb(167 139 250 / 10%); }

.evidence-section { min-height: 420px; }
.evidence-list { margin-top: 22px; }
.evidence-item { display: grid; grid-template-columns: 20px minmax(0, 1fr); gap: 10px; }
.evidence-item__rail { display: flex; flex-direction: column; align-items: center; }
.status-dot { flex: 0 0 auto; width: 8px; height: 8px; margin-top: 5px; border-radius: 999px; }
.status-dot--fresh { background: #22c55e; box-shadow: 0 0 0 4px rgb(34 197 94 / 10%); }
.status-dot--stale { background: #f59e0b; box-shadow: 0 0 0 4px rgb(245 158 11 / 10%); }
.evidence-line { width: 1px; flex: 1; min-height: 28px; margin-top: 8px; background: var(--line-subtle); }
.evidence-item:last-child .evidence-line { background: transparent; }
.evidence-item__body { margin-bottom: 12px; padding: 15px 16px; border: 1px solid var(--line-subtle); border-radius: 12px; background: var(--surface-panel); }
.evidence-meta { display: flex; flex-wrap: wrap; gap: 7px 12px; color: var(--text-subtle); font-size: 10px; }
.fresh-text { color: #22c55e; }.stale-text { color: #f59e0b; }
.evidence-item h4 { margin: 9px 0 0; color: var(--text-strong); font-size: 13px; font-weight: 600; line-height: 1.5; }
.evidence-item p { margin: 6px 0 0; color: var(--text-subtle); font-size: 10px; overflow-wrap: anywhere; }
.evidence-actions { display: flex; flex-wrap: wrap; gap: 9px; margin-top: 13px; }
.evidence-actions a { padding: 7px 10px; color: var(--text-default); font-size: 11px; border: 1px solid var(--line-subtle); border-radius: 8px; background: var(--surface-soft); }
.evidence-actions a:hover { color: var(--accent-strong); border-color: var(--accent-border); }
.empty-evidence { padding: 40px; color: var(--text-muted); text-align: center; border: 1px dashed var(--line-strong); border-radius: 14px; }

.review-section,.knowledge-section { min-height: 420px; }
.revision-pill { padding: 5px 8px; color: var(--accent-strong); font-size: 10px; border-radius: 7px; background: var(--accent-soft); }
.section-note { margin: 10px 0 0; color: var(--text-muted); font-size: 11px; line-height: 1.7; }
.review-form { display: grid; gap: 14px; margin-top: 20px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.review-form label { display: block; }
.review-form label > span,.knowledge-search > label { display: block; margin-bottom: 7px; color: var(--text-muted); font-size: 11px; }
.review-form input,.review-form select,.review-form textarea,.knowledge-search input { width: 100%; padding: 10px 11px; color: var(--text-default); font: inherit; font-size: 12px; border: 1px solid var(--line-subtle); border-radius: 9px; outline: none; background: var(--surface-panel); }
.review-form textarea { resize: vertical; line-height: 1.65; }
.review-form input:focus,.review-form select:focus,.review-form textarea:focus,.knowledge-search input:focus { border-color: var(--accent-border); box-shadow: 0 0 0 3px var(--accent-soft); }
.form-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-top: 5px; }
.form-actions > span,.knowledge-actions > span { color: var(--text-subtle); font-size: 10px; }
.primary-action { display: inline-flex; align-items: center; justify-content: center; gap: 8px; min-height: 36px; padding: 0 14px; color: var(--accent-button-text); font-size: 11px; border-radius: 9px; background: var(--accent-primary); }
.primary-action:disabled,.knowledge-search button:disabled { cursor: not-allowed; opacity: .45; }
.action-error { padding: 10px 12px; color: #f87171; font-size: 11px; border: 1px solid rgb(239 68 68 / 20%); border-radius: 9px; background: rgb(239 68 68 / 8%); }
.knowledge-status-card { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; padding: 18px; border: 1px solid var(--line-subtle); border-radius: 14px; background: var(--surface-panel); }
.knowledge-status-card h3 { margin: 6px 0 0; color: var(--text-strong); font-size: 15px; }
.knowledge-status-card p:last-child { margin: 8px 0 0; color: var(--text-muted); font-size: 11px; line-height: 1.6; }
.connection-dot { flex: 0 0 auto; width: 9px; height: 9px; margin-top: 5px; border-radius: 50%; background: #f59e0b; box-shadow: 0 0 0 5px rgb(245 158 11 / 10%); }
.connection-dot--ready { background: #22c55e; box-shadow: 0 0 0 5px rgb(34 197 94 / 10%); }
.sync-record { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
.sync-record div { padding: 11px; border-radius: 9px; background: var(--surface-soft); }
.sync-record span,.sync-record strong { display: block; }
.sync-record span { color: var(--text-subtle); font-size: 9px; }.sync-record strong { margin-top: 5px; color: var(--text-default); font-size: 11px; }
.knowledge-actions { display: flex; align-items: center; gap: 12px; margin-top: 15px; }
.knowledge-search { margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--line-subtle); }
.knowledge-search > div { display: flex; gap: 8px; }
.knowledge-search button { flex: 0 0 auto; padding: 0 14px; color: var(--text-strong); font-size: 11px; border: 1px solid var(--line-subtle); border-radius: 9px; background: var(--surface-soft); }
.knowledge-search button i { margin-right: 6px; }
.knowledge-search small,.search-caption { display: block; margin-top: 7px; color: var(--text-subtle); font-size: 9px; }
.knowledge-results { display: grid; gap: 9px; margin-top: 14px; }
.knowledge-hit { padding: 14px; border: 1px solid var(--line-subtle); border-radius: 11px; background: var(--surface-panel); }
.knowledge-hit > div { display: flex; justify-content: space-between; gap: 12px; }
.knowledge-hit strong { color: var(--text-strong); font-size: 12px; }.knowledge-hit span { color: var(--accent-strong); font-size: 9px; }
.knowledge-hit p { display: -webkit-box; margin: 9px 0 0; overflow: hidden; color: var(--text-muted); font-size: 11px; line-height: 1.65; -webkit-box-orient: vertical; -webkit-line-clamp: 5; }

@keyframes drawer-in { from { transform: translateX(24px); opacity: .5; } to { transform: translateX(0); opacity: 1; } }

@media (max-width: 640px) {
  .drawer-header { padding: 20px 18px 16px; }
  .drawer-header h2 { font-size: 19px; }
  .drawer-tabs { padding: 0 18px; }
  .drawer-content { padding: 18px 14px 30px; }
  .brief-grid { grid-template-columns: 1fr; }
  .signal-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .form-grid { grid-template-columns: 1fr; }
  .form-actions,.knowledge-actions { align-items: stretch; flex-direction: column; }
  .sync-record { grid-template-columns: 1fr; }
  .section-heading > p { display: none; }
}
</style>
