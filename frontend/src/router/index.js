import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

// 视图组件懒加载
const HotListView = () => import('../views/HotListView.vue')
const PushConfigView = () => import('../views/PushConfigView.vue')
const DataSourcesView = () => import('../views/DataSourcesView.vue')
const TrendView = () => import('../views/TrendView.vue')
const PushRulesView = () => import('../views/PushRulesView.vue')
const PushHistoryView = () => import('../views/PushHistoryView.vue')
const SchedulerView = () => import('../views/SchedulerView.vue')
const UserManagementView = () => import('../views/UserManagementView.vue')
const HotspotDashboardView = () => import('../views/HotspotDashboardView.vue')

// 登录页由 App.vue 独立渲染，这里只用于承载 /login 路由状态
const LoginRoutePlaceholder = { render: () => null }

const routes = [
    {
        path: '/',
        redirect: '/hotlist'
    },
    {
        path: '/hotlist',
        name: 'hotlist',
        component: HotListView,
        meta: { title: '热点发现', subtitle: '浏览各平台当前热点榜单', icon: 'fas fa-fire', public: true }
    },
    {
        path: '/login',
        name: 'login',
        component: LoginRoutePlaceholder,
        meta: { title: '登录', public: true }
    },
    {
        path: '/sources',
        name: 'sources',
        component: DataSourcesView,
        meta: { title: '数据源管理', subtitle: '查看采集来源与可用状态', icon: 'fas fa-rss' }
    },
    {
        path: '/intelligence',
        name: 'intelligence',
        component: HotspotDashboardView,
        meta: { title: '情报总览', subtitle: '跨平台事件、趋势生命周期与原始证据', icon: 'fas fa-radar' }
    },
    {
        path: '/trends',
        name: 'trends',
        component: TrendView,
        meta: { title: '趋势分析', subtitle: '查看热点排名与历史变化', icon: 'fas fa-chart-line' }
    },
    {
        path: '/push',
        name: 'push',
        component: PushConfigView,
        meta: { title: '推送配置', subtitle: '配置推送渠道', icon: 'fas fa-paper-plane', adminOnly: true }
    },
    {
        path: '/rules',
        name: 'rules',
        component: PushRulesView,
        meta: { title: '推送规则', subtitle: '配置推送规则', icon: 'fas fa-filter', adminOnly: true }
    },
    {
        path: '/history',
        name: 'history',
        component: PushHistoryView,
        meta: { title: '推送历史', subtitle: '查看推送记录', icon: 'fas fa-history', adminOnly: true }
    },
    {
        path: '/scheduler',
        name: 'scheduler',
        component: SchedulerView,
        meta: { title: '定时任务', subtitle: '管理定时任务', icon: 'fas fa-clock', adminOnly: true }
    },
    {
        path: '/users',
        name: 'users',
        component: UserManagementView,
        meta: { title: '用户管理', subtitle: '管理系统用户', icon: 'fas fa-users-cog', adminOnly: true }
    }
]

const router = createRouter({
    history: createWebHistory(),
    routes
})

// 路由守卫
router.beforeEach(async (to, from, next) => {
    const authStore = useAuthStore()

    // 有本地 token 时先恢复登录态，避免刷新后误判为未登录
    if (authStore.token && !authStore.isAuthenticated) {
        await authStore.checkAuth()
    }

    if (to.name === 'login' && authStore.isAuthenticated) {
        next('/intelligence')
        return
    }

    if (!to.meta.public && !authStore.isAuthenticated) {
        next({ path: '/login', query: { redirect: to.fullPath } })
        return
    }

    // 检查是否需要管理员权限
    if (to.meta.adminOnly && !authStore.isAdmin) {
        next('/hotlist')
        return
    }

    next()
})

export default router
