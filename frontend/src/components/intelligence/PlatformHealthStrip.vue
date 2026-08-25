<template>
  <section class="platform-strip" aria-label="平台采集状态">
    <button
      v-for="platform in platforms"
      :key="platform.platform"
      type="button"
      :class="['platform-signal', { 'platform-signal--active': activePlatform === platform.platform }]"
      @click="$emit('select', platform.platform)"
    >
      <span :class="['status-dot', `status-dot--${platform.status}`]" aria-hidden="true"></span>
      <span class="platform-signal__body">
        <span class="platform-signal__name">{{ platformName(platform.platform) }}</span>
        <span class="platform-signal__meta">
          {{ platformStatusLabel(platform.status) }} · {{ formatAgeMinutes(platform.data_age_minutes) }}
        </span>
      </span>
      <span class="platform-signal__provider">{{ platform.winning_provider_id || '无可用 Provider' }}</span>
    </button>
  </section>
</template>

<script setup>
import { formatAgeMinutes, platformName, platformStatusLabel } from '../../utils/hotspotDashboard'

defineProps({
  platforms: { type: Array, required: true },
  activePlatform: { type: String, default: '' },
})

defineEmits(['select'])
</script>

<style scoped>
.platform-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  overflow: hidden;
  border: 1px solid var(--line-subtle);
  border-radius: 16px;
  background: var(--surface-panel);
  box-shadow: var(--shadow-panel);
}

.platform-signal {
  position: relative;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 0 10px;
  min-width: 0;
  padding: 14px 16px;
  text-align: left;
  border-right: 1px solid var(--line-subtle);
  transition: background-color 160ms ease;
}

.platform-signal:last-child { border-right: 0; }
.platform-signal:hover,
.platform-signal--active { background: var(--surface-hover); }
.platform-signal--active::after {
  content: '';
  position: absolute;
  right: 14px;
  bottom: 0;
  left: 14px;
  height: 2px;
  border-radius: 2px;
  background: var(--accent-primary);
}

.status-dot {
  width: 8px;
  height: 8px;
  margin-top: 6px;
  border-radius: 999px;
  background: #64748b;
  box-shadow: 0 0 0 4px rgb(100 116 139 / 10%);
}
.status-dot--fresh { background: #22c55e; box-shadow: 0 0 0 4px rgb(34 197 94 / 12%); }
.status-dot--stale { background: #f59e0b; box-shadow: 0 0 0 4px rgb(245 158 11 / 12%); }
.status-dot--failed { background: #ef4444; box-shadow: 0 0 0 4px rgb(239 68 68 / 12%); }

.platform-signal__body { min-width: 0; }
.platform-signal__name {
  display: block;
  color: var(--text-strong);
  font-size: 13px;
  font-weight: 650;
}
.platform-signal__meta,
.platform-signal__provider {
  display: block;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.5;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.platform-signal__provider {
  grid-column: 2;
  margin-top: 4px;
  color: var(--text-subtle);
}

@media (max-width: 900px) {
  .platform-strip {
    display: flex;
    overflow-x: auto;
    scroll-snap-type: x proximity;
  }
  .platform-signal {
    flex: 0 0 210px;
    scroll-snap-align: start;
  }
}
</style>
