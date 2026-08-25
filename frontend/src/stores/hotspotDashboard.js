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
  const annotationSaving = ref(false)
  const knowledgeLoading = ref(false)
  const knowledgeHits = ref([])
  const knowledgeQuery = ref('')
  const error = ref('')
  const actionError = ref('')

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
    actionError.value = ''
    knowledgeHits.value = []
    knowledgeQuery.value = ''
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
    knowledgeHits.value = []
    actionError.value = ''
  }

  async function saveAnnotation(eventId, payload) {
    annotationSaving.value = true
    actionError.value = ''
    try {
      const annotation = await apiCall(`/v1/hotspots/events/${eventId}/annotation`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (selectedEvent.value?.event_id === eventId) {
        selectedEvent.value = { ...selectedEvent.value, annotation }
      }
      return annotation
    } catch (reason) {
      actionError.value = reason?.message || '人工标记保存失败'
      return null
    } finally {
      annotationSaving.value = false
    }
  }

  async function syncKnowledge(eventId) {
    knowledgeLoading.value = true
    actionError.value = ''
    try {
      const result = await apiCall(`/v1/hotspots/events/${eventId}/knowledge/sync`, {
        method: 'POST',
      })
      if (selectedEvent.value?.event_id === eventId) {
        selectedEvent.value = { ...selectedEvent.value, knowledge_sync: result.sync }
      }
      return result
    } catch (reason) {
      actionError.value = reason?.message || '同步 WeKnora 失败'
      return null
    } finally {
      knowledgeLoading.value = false
    }
  }

  async function searchKnowledge(eventId, query = '') {
    knowledgeLoading.value = true
    actionError.value = ''
    try {
      const result = await apiCall(`/v1/hotspots/events/${eventId}/knowledge/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim() || null, match_count: 8 }),
      })
      knowledgeHits.value = result.hits || []
      knowledgeQuery.value = result.query || query
      return result
    } catch (reason) {
      actionError.value = reason?.message || 'WeKnora 检索失败'
      return null
    } finally {
      knowledgeLoading.value = false
    }
  }

  return {
    overview,
    events,
    selectedEvent,
    loading,
    detailLoading,
    annotationSaving,
    knowledgeLoading,
    knowledgeHits,
    knowledgeQuery,
    error,
    actionError,
    refresh,
    openEvent,
    closeEvent,
    saveAnnotation,
    syncKnowledge,
    searchKnowledge,
  }
})
