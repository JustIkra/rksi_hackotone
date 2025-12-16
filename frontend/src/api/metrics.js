/**
 * Metrics API endpoints
 */

import apiClient from './client'

export const metricsApi = {
  // MetricDef endpoints

  /**
   * Получить список всех определений метрик
   * @param {boolean} activeOnly - Только активные метрики
   */
  async listMetricDefs(activeOnly = false) {
    const response = await apiClient.get('/metric-defs', {
      params: { active_only: activeOnly }
    })
    return response.data
  },

  /**
   * Получить определение метрики по ID
   * @param {string} metricDefId - UUID метрики
   */
  async getMetricDef(metricDefId) {
    const response = await apiClient.get(`/metric-defs/${metricDefId}`)
    return response.data
  },

  /**
   * Создать определение метрики
   * @param {Object} metricDef - Данные метрики
   */
  async createMetricDef(metricDef) {
    const response = await apiClient.post('/metric-defs', metricDef)
    return response.data
  },

  /**
   * Обновить определение метрики
   * @param {string} metricDefId - UUID метрики
   * @param {Object} updates - Обновляемые данные
   */
  async updateMetricDef(metricDefId, updates) {
    const response = await apiClient.put(`/metric-defs/${metricDefId}`, updates)
    return response.data
  },

  /**
   * Удалить определение метрики
   * @param {string} metricDefId - UUID метрики
   */
  async deleteMetricDef(metricDefId) {
    const response = await apiClient.delete(`/metric-defs/${metricDefId}`)
    return response.data
  },

  // ExtractedMetric endpoints

  /**
   * Получить извлечённые метрики для отчёта
   * @param {string} reportId - UUID отчёта
   */
  async listExtractedMetrics(reportId) {
    const response = await apiClient.get(`/reports/${reportId}/metrics`)
    return response.data
  },

  /**
   * Создать или обновить извлечённую метрику
   * @param {string} reportId - UUID отчёта
   * @param {Object} metric - Данные метрики
   */
  async createOrUpdateExtractedMetric(reportId, metric) {
    const response = await apiClient.post(`/reports/${reportId}/metrics`, metric)
    return response.data
  },

  /**
   * Массовое создание/обновление метрик
   * @param {string} reportId - UUID отчёта
   * @param {Array} metrics - Массив метрик
   */
  async bulkCreateExtractedMetrics(reportId, metrics) {
    const response = await apiClient.post(`/reports/${reportId}/metrics/bulk`, {
      metrics
    })
    return response.data
  },

  /**
   * Обновить значение метрики
   * @param {string} reportId - UUID отчёта
   * @param {string} metricDefId - UUID определения метрики
   * @param {number} value - Новое значение
   * @param {string} notes - Заметки (опционально)
   */
  async updateExtractedMetric(reportId, metricDefId, value, notes = null) {
    const response = await apiClient.put(
      `/reports/${reportId}/metrics/${metricDefId}`,
      { value, notes }
    )
    return response.data
  },

  /**
   * Удалить извлечённую метрику
   * @param {string} extractedMetricId - UUID извлечённой метрики
   */
  async deleteExtractedMetric(extractedMetricId) {
    const response = await apiClient.delete(`/extracted-metrics/${extractedMetricId}`)
    return response.data
  },

  /**
   * Получить шаблон метрик для отчёта (все активные метрики с текущими значениями)
   * Возвращает полный список метрик, включая пустые (для ручного ввода)
   * @param {string} reportId - UUID отчёта
   * @returns {Object} { items: [...], total, filled_count, missing_count }
   */
  async getMetricTemplate(reportId) {
    const response = await apiClient.get(`/reports/${reportId}/metrics/template`)
    return response.data
  },

  /**
   * Удалить/сбросить значение метрики (установить в null)
   * @param {string} reportId - UUID отчёта
   * @param {string} metricDefId - UUID определения метрики
   */
  async clearExtractedMetric(reportId, metricDefId) {
    const response = await apiClient.delete(`/reports/${reportId}/metrics/${metricDefId}`)
    return response.data
  }
}
