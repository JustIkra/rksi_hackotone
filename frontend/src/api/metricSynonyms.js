/**
 * Metric Synonyms API endpoints
 */

import apiClient from './client'

export const metricSynonymsApi = {
  /**
   * Получить все синонимы для метрики
   * @param {string} metricDefId - UUID метрики
   * @returns {Promise<Array>} Список синонимов
   */
  async getSynonyms(metricDefId) {
    const response = await apiClient.get(`/metric-defs/${metricDefId}/synonyms`)
    return response.data
  },

  /**
   * Добавить новый синоним к метрике
   * @param {string} metricDefId - UUID метрики
   * @param {string} synonym - текст синонима
   * @returns {Promise<Object>} Созданный синоним
   */
  async createSynonym(metricDefId, synonym) {
    const response = await apiClient.post(`/metric-defs/${metricDefId}/synonyms`, { synonym })
    return response.data
  },

  /**
   * Обновить синоним
   * @param {number} synonymId - ID синонима
   * @param {string} synonym - новый текст синонима
   * @returns {Promise<Object>} Обновленный синоним
   */
  async updateSynonym(synonymId, synonym) {
    const response = await apiClient.put(`/metric-synonyms/${synonymId}`, { synonym })
    return response.data
  },

  /**
   * Удалить синоним
   * @param {number} synonymId - ID синонима
   * @returns {Promise<void>}
   */
  async deleteSynonym(synonymId) {
    const response = await apiClient.delete(`/metric-synonyms/${synonymId}`)
    return response.data
  }
}
