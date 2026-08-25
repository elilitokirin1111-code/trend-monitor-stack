<template>
  <aside class="app-sidebar">
    <div class="brand-block">
      <div class="brand-mark" aria-hidden="true"><span></span><span></span><span></span></div>
      <div class="brand-copy">
        <h1>热点情报中心</h1>
        <p>HOTSPOT INTELLIGENCE</p>
      </div>
      <button v-if="authStore.isAuthenticated" type="button" class="mobile-logout" title="退出登录" @click="$emit('logout')">
        <i class="fas fa-arrow-right-from-bracket"></i>
      </button>
    </div>

    <nav class="sidebar-nav" aria-label="主导航">
      <section v-for="group in visibleMenuGroups" :key="group.label" class="nav-group">
        <p>{{ group.label }}</p>
        <div class="nav-group__items">
          <RouterLink
            v-for="item in group.items"
            :key="item.path"
            :to="item.path"
            :class="['nav-item', { active: isActive(item.path) }]"
          >
            <span class="nav-icon"><i :class="item.icon"></i></span>
            <span class="nav-label">{{ item.name }}</span>
            <span v-if="item.badge" class="nav-badge">{{ item.badge }}</span>
          </RouterLink>
        </div>
      </section>
    </nav>

    <div v-if="authStore.isAuthenticated" class="sidebar-context">
      <p>工作区状态</p>
      <div class="context-row"><span><i class="fas fa-database"></i>已配置数据源</span><strong>{{ appStore.stats?.sources_count || 0 }}</strong></div>
      <div class="context-row"><span><i class="fas fa-paper-plane"></i>推送渠道</span><strong>{{ appStore.stats?.configured_channels || 0 }}/{{ appStore.stats?.total_channels || 7 }}</strong></div>
    </div>

    <div v-if="authStore.isAuthenticated" class="account-block">
      <div class="account-avatar">{{ authStore.user?.username?.[0]?.toUpperCase() || 'U' }}</div>
      <div class="account-copy">
        <strong>{{ authStore.user?.username || 'User' }}</strong>
        <span>{{ authStore.isAdmin ? '系统管理员' : '情报用户' }}</span>
      </div>
      <button type="button" title="退出登录" @click="$emit('logout')"><i class="fas fa-arrow-right-from-bracket"></i></button>
    </div>

    <footer class="sidebar-footer">
      <a href="https://github.com/JackyST0/hotpush" target="_blank" rel="noopener noreferrer">基于 HotPush 架构演进 <i class="fas fa-arrow-up-right-from-square"></i></a>
    </footer>
  </aside>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '../stores/app'
import { useAuthStore } from '../stores/auth'

defineEmits(['logout', 'login'])

const route = useRoute()
const authStore = useAuthStore()
const appStore = useAppStore()

const menuGroups = [
  {
    label: '情报工作台',
    items: [
      { path: '/intelligence', name: '情报总览', icon: 'fas fa-compass', adminOnly: false },
      { path: '/hotlist', name: '热点发现', icon: 'fas fa-fire-flame-curved', adminOnly: false, public: true },
      { path: '/trends', name: '趋势分析', icon: 'fas fa-chart-line', adminOnly: false },
    ],
  },
  {
    label: '数据与交付',
    items: [
      { path: '/sources', name: '数据源', icon: 'fas fa-satellite-dish', adminOnly: false },
      { path: '/history', name: '推送历史', icon: 'fas fa-clock-rotate-left', adminOnly: true },
      { path: '/push', name: '推送配置', icon: 'fas fa-paper-plane', adminOnly: true },
    ],
  },
  {
    label: '系统管理',
    items: [
      { path: '/rules', name: '规则策略', icon: 'fas fa-list-check', adminOnly: true },
      { path: '/scheduler', name: '采集调度', icon: 'fas fa-calendar-check', adminOnly: true },
      { path: '/users', name: '用户管理', icon: 'fas fa-user-shield', adminOnly: true },
    ],
  },
]

const visibleMenuGroups = computed(() => menuGroups
  .map(group => ({
    ...group,
    items: group.items.filter(item => {
      if (!authStore.isAuthenticated) return item.public
      return !item.adminOnly || authStore.isAdmin
    }),
  }))
  .filter(group => group.items.length))

const isActive = path => route.path === path

onMounted(() => appStore.fetchStats())
</script>

<style scoped>
.app-sidebar {
  z-index: 20;
  display: flex;
  width: 246px;
  flex: 0 0 246px;
  flex-direction: column;
  height: 100vh;
  color: var(--text-default);
  background: color-mix(in srgb, var(--surface-sidebar) 97%, transparent);
  border-right: 1px solid var(--line-subtle);
  backdrop-filter: blur(18px);
}
.brand-block { display: flex; align-items: center; gap: 11px; min-height: 84px; padding: 18px 19px; border-bottom: 1px solid var(--line-subtle); }
.brand-mark { display: flex; align-items: flex-end; justify-content: center; gap: 3px; width: 34px; height: 34px; padding: 8px; border-radius: 10px; background: var(--accent-primary); box-shadow: 0 8px 20px var(--accent-soft); }
.brand-mark span { width: 4px; border-radius: 3px; background: var(--accent-button-text); }.brand-mark span:nth-child(1) { height: 7px; }.brand-mark span:nth-child(2) { height: 14px; }.brand-mark span:nth-child(3) { height: 10px; }
.brand-copy { min-width: 0; }.brand-copy h1 { margin: 0; color: var(--text-strong); font-size: 14px; font-weight: 720; letter-spacing: .01em; }.brand-copy p { margin: 3px 0 0; color: var(--text-subtle); font-size: 7px; font-weight: 750; letter-spacing: .13em; }
.mobile-logout { display: none; margin-left: auto; color: var(--text-muted); }
.sidebar-nav { flex: 1; overflow-y: auto; padding: 18px 12px; }.nav-group + .nav-group { margin-top: 23px; }.nav-group > p { margin: 0 9px 7px; color: var(--text-subtle); font-size: 8px; font-weight: 750; letter-spacing: .13em; text-transform: uppercase; }.nav-group__items { display: grid; gap: 3px; }
.nav-item { position: relative; display: flex; align-items: center; gap: 10px; min-height: 40px; padding: 7px 9px; color: var(--text-muted); border: 1px solid transparent; border-radius: 10px; transition: 150ms ease; }.nav-item:hover { color: var(--text-default); background: var(--surface-soft); }.nav-item.active { color: var(--text-strong); border-color: var(--line-subtle); background: var(--surface-hover); box-shadow: inset 3px 0 0 var(--accent-primary); }
.nav-icon { display: grid; width: 25px; height: 25px; place-items: center; color: var(--text-subtle); font-size: 11px; border-radius: 7px; }.nav-item.active .nav-icon { color: var(--accent-strong); background: var(--accent-soft); }.nav-label { font-size: 11px; font-weight: 570; }.nav-badge { margin-left: auto; padding: 2px 5px; color: var(--accent-strong); font-size: 7px; border-radius: 5px; background: var(--accent-soft); }
.sidebar-context { margin: 0 12px 13px; padding: 12px; border: 1px solid var(--line-subtle); border-radius: 12px; background: var(--surface-soft); }.sidebar-context > p { margin: 0 0 9px; color: var(--text-subtle); font-size: 8px; font-weight: 700; letter-spacing: .1em; }.context-row { display: flex; align-items: center; justify-content: space-between; color: var(--text-muted); font-size: 9px; }.context-row + .context-row { margin-top: 8px; }.context-row i { width: 15px; color: var(--text-subtle); }.context-row strong { color: var(--text-default); font-size: 10px; }
.account-block { display: flex; align-items: center; gap: 9px; padding: 13px 16px; border-top: 1px solid var(--line-subtle); }.account-avatar { display: grid; width: 30px; height: 30px; place-items: center; color: var(--accent-button-text); font-size: 10px; font-weight: 750; border-radius: 9px; background: var(--accent-primary); }.account-copy { min-width: 0; flex: 1; }.account-copy strong,.account-copy span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.account-copy strong { color: var(--text-strong); font-size: 10px; }.account-copy span { margin-top: 2px; color: var(--text-subtle); font-size: 8px; }.account-block button { color: var(--text-subtle); font-size: 10px; }.account-block button:hover { color: #f87171; }
.sidebar-footer { padding: 11px 16px; text-align: center; border-top: 1px solid var(--line-subtle); }.sidebar-footer a { color: var(--text-subtle); font-size: 8px; }.sidebar-footer a:hover { color: var(--text-muted); }.sidebar-footer i { margin-left: 3px; font-size: 7px; }

@media (max-width: 767px) {
  .app-sidebar { width: 100%; height: auto; flex: 0 0 auto; border-right: 0; border-bottom: 1px solid var(--line-subtle); }
  .brand-block { min-height: 62px; padding: 12px 14px; }.brand-mark { width: 31px; height: 31px; }.mobile-logout { display: block; }
  .sidebar-nav { display: flex; gap: 5px; padding: 0 10px 10px; overflow-x: auto; }.nav-group { margin: 0 !important; }.nav-group > p { display: none; }.nav-group__items { display: flex; gap: 5px; }.nav-item { flex: 0 0 auto; min-height: 34px; padding: 5px 9px; }.nav-icon { width: 20px; height: 20px; }.nav-label { font-size: 10px; }.sidebar-context,.account-block,.sidebar-footer { display: none; }
}
</style>
