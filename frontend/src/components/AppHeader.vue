<template>
  <header class="app-header">
    <div class="app-header__title">
      <p><span>热点情报中心</span><i class="fas fa-chevron-right"></i>{{ viewTitle }}</p>
      <h2>{{ viewTitle }}</h2>
      <span v-if="viewSubtitle">{{ viewSubtitle }}</span>
    </div>

    <div class="app-header__actions">
      <span v-if="lastUpdate" class="last-update"><i class="far fa-clock"></i>{{ lastUpdate }} 刷新</span>
      <button
        v-if="showRefresh"
        type="button"
        class="header-action"
        title="刷新当前数据"
        @click="$emit('refresh')"
      >
        <i class="fas fa-rotate"></i><span>刷新</span>
      </button>
      <button
        type="button"
        class="header-action header-action--icon"
        :title="isDarkMode ? '切换到浅色模式' : '切换到深色模式'"
        @click="toggleDarkMode"
      >
        <i :class="isDarkMode ? 'fas fa-sun' : 'fas fa-moon'"></i>
      </button>
      <button
        v-if="showLogin"
        type="button"
        class="header-action header-action--primary"
        @click="$emit('login')"
      >
        <i class="fas fa-arrow-right-to-bracket"></i><span>登录</span>
      </button>
    </div>
  </header>
</template>

<script setup>
import { useTheme } from '../composables/useTheme'

defineProps({
  viewTitle: String,
  viewSubtitle: String,
  lastUpdate: String,
  showRefresh: { type: Boolean, default: false },
  showLogin: { type: Boolean, default: false },
})

defineEmits(['refresh', 'login'])

const { isDarkMode, toggleDarkMode } = useTheme()
</script>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  min-height: 84px;
  margin-bottom: 2px;
  padding: 12px 2px;
}
.app-header__title { min-width: 0; }
.app-header__title p {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0 0 3px;
  color: var(--text-subtle);
  font-size: 9px;
  font-weight: 650;
  letter-spacing: .06em;
  text-transform: uppercase;
}
.app-header__title p span { color: var(--accent-strong); }
.app-header__title p i { font-size: 7px; }
.app-header__title h2 { display: inline; margin: 0; color: var(--text-strong); font-size: 19px; font-weight: 680; letter-spacing: -.015em; }
.app-header__title > span { margin-left: 10px; color: var(--text-muted); font-size: 11px; }
.app-header__actions { display: flex; align-items: center; gap: 7px; }
.last-update { margin-right: 4px; color: var(--text-subtle); font-size: 10px; }.last-update i { margin-right: 5px; }
.header-action {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  height: 34px;
  padding: 0 11px;
  color: var(--text-muted);
  font-size: 11px;
  border: 1px solid var(--line-subtle);
  border-radius: 9px;
  background: var(--surface-panel);
}
.header-action:hover { color: var(--text-strong); border-color: var(--line-strong); }
.header-action--icon { width: 34px; padding: 0; }
.header-action--primary { color: var(--accent-button-text); border-color: var(--accent-primary); background: var(--accent-primary); }

@media (max-width: 640px) {
  .app-header { min-height: 70px; }
  .app-header__title > span,.app-header__title p { display: none; }
  .last-update { display: none; }
  .header-action span { display: none; }
  .header-action { width: 34px; padding: 0; }
}
</style>
