/**
 * Admin API endpoints
 */

import apiClient from './client'

export const adminApi = {
  /**
   * Получить список пользователей со статусом PENDING
   */
  async getPendingUsers() {
    const response = await apiClient.get('/admin/pending-users')
    return response.data
  },

  /**
   * Получить список всех пользователей
   */
  async getAllUsers() {
    const response = await apiClient.get('/admin/users')
    return response.data
  },

  /**
   * Одобрить пользователя (PENDING -> ACTIVE)
   * @param {string} userId - UUID
   */
  async approveUser(userId) {
    const response = await apiClient.post(`/admin/approve/${userId}`)
    return response.data
  },

  /**
   * Назначить пользователя администратором
   * @param {string} userId - UUID
   */
  async makeAdmin(userId) {
    const response = await apiClient.post(`/admin/make-admin/${userId}`)
    return response.data
  },

  /**
   * Удалить пользователя
   * @param {string} userId - UUID
   */
  async deleteUser(userId) {
    const response = await apiClient.delete(`/admin/users/${userId}`)
    return response.data
  },

  /**
   * Снять права администратора
   * @param {string} userId - UUID
   */
  async revokeAdmin(userId) {
    const response = await apiClient.post(`/admin/revoke-admin/${userId}`)
    return response.data
  },

  /**
   * Получить журнал аудита
   * @param {Object} params - Параметры запроса
   * @param {string} [params.start_date] - Фильтр по начальной дате
   * @param {string} [params.end_date] - Фильтр по конечной дате
   * @param {string} [params.action] - Фильтр по типу действия
   * @param {number} [params.limit=50] - Максимум записей
   * @param {number} [params.offset=0] - Смещение для пагинации
   */
  async getAuditLog(params = {}) {
    const response = await apiClient.get('/admin/audit-log', { params })
    return response.data
  },

  /**
   * Получить список типов действий для фильтра
   */
  async getAuditActionTypes() {
    const response = await apiClient.get('/admin/audit-log/actions')
    return response.data
  },

  // ==================== Embedding / Semantic Search ====================

  /**
   * Полная переиндексация всех метрик для semantic search
   */
  async reindexAllMetrics() {
    const response = await apiClient.post('/admin/metrics/reindex')
    return response.data
  },

  /**
   * Переиндексировать одну метрику
   * @param {string} metricId - UUID метрики
   */
  async reindexMetric(metricId) {
    const response = await apiClient.post(`/admin/metrics/${metricId}/reindex`)
    return response.data
  },

  /**
   * Поиск похожих метрик по тексту
   * @param {string} query - Текст для поиска
   * @param {number} [topK=5] - Количество результатов
   * @param {number} [threshold=0.5] - Минимальный порог сходства
   */
  async searchSimilarMetrics(query, topK = 5, threshold = 0.5) {
    const response = await apiClient.post('/admin/metrics/search-similar', null, {
      params: { query, top_k: topK, threshold }
    })
    return response.data
  },

  /**
   * Получить статистику embedding индекса
   */
  async getEmbeddingStats() {
    const response = await apiClient.get('/admin/metrics/embedding-stats')
    return response.data
  }
}
