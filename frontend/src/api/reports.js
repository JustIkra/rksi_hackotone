/**
 * Reports API endpoints
 */

import apiClient from './client'

export const reportsApi = {
  /**
   * Загрузить отчёт для участника
   * @param {string} participantId - UUID
   * @param {File} file - DOCX файл
   */
  async upload(participantId, file) {
    const formData = new FormData()
    formData.append('file', file)

    const response = await apiClient.post(`/participants/${participantId}/reports`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
    return response.data
  },

  /**
   * Скачать отчёт
   * @param {string} reportId - UUID
   */
  async download(reportId) {
    const response = await apiClient.get(`/reports/${reportId}/download`, {
      responseType: 'blob'
    })
    return response
  },

  /**
   * Получить детали отчёта
   * @param {string} reportId - UUID
   */
  async getById(reportId) {
    const response = await apiClient.get(`/reports/${reportId}`)
    return response.data
  },

  /**
   * Удалить отчёт
   * @param {string} reportId - UUID
   */
  async delete(reportId) {
    const response = await apiClient.delete(`/reports/${reportId}`)
    return response.data
  },

  /**
   * Запустить извлечение метрик
   * @param {string} reportId - UUID
   */
  async extract(reportId) {
    const response = await apiClient.post(`/reports/${reportId}/extract`)
    return response.data
  },

  /**
   * Получить извлечённые метрики отчёта
   * @param {string} reportId - UUID
   */
  async getMetrics(reportId) {
    const response = await apiClient.get(`/reports/${reportId}/metrics`)
    return response.data
  },

  /**
   * Get all reports for a participant
   * @param {string} participantId - UUID
   */
  async getList(participantId) {
    const response = await apiClient.get(`/participants/${participantId}/reports`)
    return response.data
  }
}
