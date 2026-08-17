import { defineStore } from 'pinia'
import { ref } from 'vue'

import { useApi } from '../composables/useApi'
import { buildEventQuery } from '../utils/hotspotDashboard'


export const useHotspotDashboardStore = defineStore('hotspotDashboard', () => {
  const { apiCall } = useApi()
  const overview = ref(null)
  const events = ref({ total: 0, limit: 20, offset: 0, items: [] })
  const selectedEvent = ref(null)
  const loading = ref(false)
  const detailLoading = ref(false)
  const error = ref('')

  async function refresh(filters) {
    loading.value = true
    error.value = ''
    try {
      const query = buildEventQuery(filters)
      const [overviewData, eventData] = await Promise.all([
        apiCall('/v1/hotspots/overview'),
        apiCall(`/v1/hotspots/events?${query}`),
      ])
      overview.value = overviewData
      events.value = eventData
    } catch (reason) {
      error.value = reason?.message || '热点情报加载失败'
    } finally {
      loading.value = false
    }
  }

  async function openEvent(eventId) {
    detailLoading.value = true
    error.value = ''
    try {
      selectedEvent.value = await apiCall(`/v1/hotspots/events/${eventId}`)
    } catch (reason) {
      error.value = reason?.message || '事件证据加载失败'
    } finally {
      detailLoading.value = false
    }
  }

  function closeEvent() {
    selectedEvent.value = null
  }

  return { overview, events, selectedEvent, loading, detailLoading, error, refresh, openEvent, closeEvent }
})
