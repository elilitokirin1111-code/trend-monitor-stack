<template>
    <div :class="['gradient-bg min-h-screen text-white', !isDarkMode && 'light-mode']">
        <!-- Login Page -->
        <LoginPage v-if="isLoginRoute" @login-success="handleLoginSuccess" />

        <!-- Main App -->
        <div v-else class="app-shell flex min-h-screen flex-col md:h-screen md:flex-row">
            <!-- Sidebar -->
            <Sidebar @logout="handleLogout" @login="handleLoginClick" />

            <!-- Main Content -->
            <main class="app-main flex-1 overflow-auto px-3 pb-3 pt-2 sm:px-4 sm:pb-4 md:px-6 md:pb-6 lg:px-8">
                <!-- Header -->
                <AppHeader
                    :view-title="currentRoute?.meta?.title || '热搜榜'"
                    :view-subtitle="currentRoute?.meta?.subtitle || ''"
                    :last-update="appStore.lastUpdate"
                    :show-refresh="['hotlist', 'intelligence'].includes(currentRoute?.name)"
                    :show-login="!authStore.isAuthenticated"
                    @refresh="handleRefresh"
                    @login="handleLoginClick"
                />

                <!-- Router View with Transition -->
                <RouterView v-slot="{ Component }">
                    <Transition name="fade" mode="out-in">
                        <component :is="Component" />
                    </Transition>
                </RouterView>
            </main>
        </div>

        <!-- Toast Container -->
        <ToastContainer />

        <!-- Global Confirm Dialog -->
        <div v-if="confirmState.visible" class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div class="glass rounded-2xl w-full max-w-sm overflow-hidden">
                <div class="p-6">
                    <div class="flex items-start space-x-4">
                        <div :class="['w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0', confirmState.type === 'danger' ? 'bg-red-500/20' : 'bg-amber-500/20']">
                            <i :class="[confirmState.type === 'danger' ? 'fas fa-trash-alt text-red-400' : 'fas fa-exclamation-triangle text-amber-400']"></i>
                        </div>
                        <div class="flex-1">
                            <h3 class="font-semibold text-white">{{ confirmState.title }}</h3>
                            <p class="text-gray-400 text-sm mt-1">{{ confirmState.message }}</p>
                        </div>
                    </div>
                </div>
                <div class="px-6 pb-5 flex justify-end space-x-3">
                    <button
                        @click="handleConfirmCancel"
                        class="px-4 py-2 text-sm text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition"
                    >
                        {{ confirmState.cancelText }}
                    </button>
                    <button
                        @click="handleConfirmOk"
                        :class="[
                            'px-4 py-2 text-sm rounded-lg transition font-medium',
                            confirmState.type === 'danger' 
                                ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30' 
                                : 'bg-gradient-to-r from-amber-500 to-orange-500 text-white hover:opacity-90'
                        ]"
                    >
                        {{ confirmState.confirmText }}
                    </button>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import { computed, onMounted, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { useAppStore } from './stores/app'
import { useTheme } from './composables/useTheme'
import { useToast } from './composables/useToast'
import { useConfirm } from './composables/useConfirm'

// Components
import LoginPage from './components/LoginPage.vue'
import Sidebar from './components/Sidebar.vue'
import AppHeader from './components/AppHeader.vue'
import ToastContainer from './components/ToastContainer.vue'

// Stores
const authStore = useAuthStore()
const appStore = useAppStore()

// Composables
const { isDarkMode } = useTheme()
const { showToast } = useToast()
const { confirmState, handleConfirm: handleConfirmOk, handleCancel: handleConfirmCancel } = useConfirm()
const route = useRoute()
const router = useRouter()

// Computed
const currentRoute = computed(() => route)
const isLoginRoute = computed(() => route.name === 'login')

// Provide stores to child components
provide('authStore', authStore)
provide('appStore', appStore)

// Methods
const handleLoginSuccess = () => {
    showToast('登录成功', 'success')
    appStore.fetchStats()
    router.push(route.query.redirect || '/intelligence')
}

const handleLogout = () => {
    authStore.logout()
    showToast('已退出登录', 'success')
    router.push('/hotlist')
}

const handleLoginClick = () => {
    router.push({
        path: '/login',
        query: { redirect: route.fullPath === '/login' ? '/hotlist' : route.fullPath }
    })
}

const handleRefresh = () => {
    appStore.triggerRefresh()
    appStore.fetchStats()
}

// Lifecycle
onMounted(async () => {
    await authStore.checkAuth()
    // 无论是否登录都获取统计信息（公开接口）
    appStore.fetchStats()
    if (authStore.isAuthenticated) {
        appStore.updateLastRefresh()
    }
})
</script>

<style>
.fade-enter-active,
.fade-leave-active {
    transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
    opacity: 0;
}
</style>
