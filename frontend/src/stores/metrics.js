/**
 * Metrics Store - кэширование и управление метриками
 * Prevents duplicate API calls across components
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { metricsApi } from '@/api'
import { normalizeApiError } from '@/utils/normalizeError'

export const useMetricsStore = defineStore('metrics', () => {
  const metricDefs = ref([])
  const loading = ref(false)
  const error = ref(null)
  const lastFetched = ref(null)

  // Cache TTL: 5 minutes
  const CACHE_TTL = 5 * 60 * 1000

  const isStale = computed(() => {
    if (!lastFetched.value) return true
    return Date.now() - lastFetched.value > CACHE_TTL
  })

  const hasData = computed(() => metricDefs.value.length > 0)

  /**
   * Fetch metric definitions with caching
   * @param {Object} options
   * @param {boolean} options.force - Force refresh even if cached
   * @param {boolean} options.activeOnly - Only fetch active metrics
   */
  async function fetchMetricDefs({ force = false, activeOnly = false } = {}) {
    // Return cached data if not stale and not forced
    if (!force && hasData.value && !isStale.value) {
      return metricDefs.value
    }

    // Prevent duplicate concurrent requests
    if (loading.value) {
      // Wait for current request to complete
      return new Promise((resolve) => {
        const check = setInterval(() => {
          if (!loading.value) {
            clearInterval(check)
            resolve(metricDefs.value)
          }
        }, 50)
      })
    }

    loading.value = true
    error.value = null

    try {
      const data = await metricsApi.listMetricDefs(activeOnly)
      metricDefs.value = data
      lastFetched.value = Date.now()
      return data
    } catch (err) {
      const normalized = normalizeApiError(err, 'Ошибка загрузки метрик')
      error.value = normalized.message
      err.normalizedError = normalized
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Get metric definition by ID (from cache)
   * @param {string} id - Metric definition UUID
   */
  function getMetricDefById(id) {
    return metricDefs.value.find(m => m.id === id)
  }

  /**
   * Get metric name by ID (from cache)
   * @param {string} id - Metric definition UUID
   */
  function getMetricName(id) {
    const metric = getMetricDefById(id)
    return metric?.name_ru || metric?.name || id
  }

  /**
   * Invalidate cache (call after mutations)
   */
  function invalidateCache() {
    lastFetched.value = null
  }

  /**
   * Update metric in cache
   * @param {Object} updatedMetric - Updated metric data
   */
  function updateInCache(updatedMetric) {
    const index = metricDefs.value.findIndex(m => m.id === updatedMetric.id)
    if (index !== -1) {
      metricDefs.value[index] = updatedMetric
    }
  }

  /**
   * Remove metric from cache
   * @param {string} id - Metric definition UUID
   */
  function removeFromCache(id) {
    metricDefs.value = metricDefs.value.filter(m => m.id !== id)
  }

  /**
   * Add metric to cache
   * @param {Object} metric - New metric data
   */
  function addToCache(metric) {
    metricDefs.value.push(metric)
  }

  return {
    metricDefs,
    loading,
    error,
    isStale,
    hasData,
    fetchMetricDefs,
    getMetricDefById,
    getMetricName,
    invalidateCache,
    updateInCache,
    removeFromCache,
    addToCache
  }
})
