/**
 * API client for AI metric generation from PDF/DOCX reports.
 *
 * Provides methods for:
 * - Starting metric generation from uploaded files
 * - Polling task status/progress
 * - Fetching pending metrics for moderation
 * - Approving/rejecting generated metrics
 */

import { apiClient as api } from './index.js'

/**
 * Start metric generation from uploaded PDF/DOCX file.
 *
 * @param {File} file - PDF or DOCX file to process
 * @returns {Promise<{task_id: string, message: string}>}
 */
export async function startMetricGeneration(file) {
  const formData = new FormData()
  formData.append('file', file)

  const response = await api.post('/admin/metrics/generate', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  return response.data
}

/**
 * Get status and progress of metric generation task.
 *
 * @param {string} taskId - Celery task ID
 * @returns {Promise<{
 *   task_id: string,
 *   status: 'pending'|'processing'|'completed'|'failed',
 *   progress: number,
 *   current_step?: string,
 *   total_pages?: number,
 *   processed_pages?: number,
 *   metrics_found?: number,
 *   error?: string,
 *   result?: object
 * }>}
 */
export async function getGenerationStatus(taskId) {
  const response = await api.get(`/admin/metrics/generate/${taskId}/status`)
  return response.data
}

/**
 * Poll generation status until completion or failure.
 *
 * @param {string} taskId - Celery task ID
 * @param {function} onProgress - Callback for progress updates
 * @param {number} intervalMs - Polling interval in milliseconds (default: 2000)
 * @returns {Promise<object>} - Final result when completed
 * @throws {Error} - If task fails
 */
export async function pollGenerationStatus(taskId, onProgress = null, intervalMs = 2000) {
  return new Promise((resolve, reject) => {
    const poll = async () => {
      try {
        const status = await getGenerationStatus(taskId)

        if (onProgress) {
          onProgress(status)
        }

        if (status.status === 'completed') {
          resolve(status.result || status)
        } else if (status.status === 'failed') {
          reject(new Error(status.error || 'Generation failed'))
        } else {
          setTimeout(poll, intervalMs)
        }
      } catch (error) {
        reject(error)
      }
    }

    poll()
  })
}

/**
 * Get list of metrics pending moderation.
 *
 * @param {object} params - Query parameters
 * @param {number} params.limit - Max items (default: 50)
 * @param {number} params.offset - Skip items (default: 0)
 * @returns {Promise<{items: Array, total: number}>}
 */
export async function getPendingMetrics(params = {}) {
  const response = await api.get('/admin/metrics/pending', { params })
  return response.data
}

/**
 * Approve a pending metric.
 *
 * @param {string} metricId - Metric UUID
 * @returns {Promise<{id: string, code: string, name: string, moderation_status: string, message: string}>}
 */
export async function approveMetric(metricId) {
  const response = await api.post(`/admin/metrics/${metricId}/approve`)
  return response.data
}

/**
 * Reject a pending metric.
 *
 * @param {string} metricId - Metric UUID
 * @param {string} reason - Optional rejection reason
 * @returns {Promise<{id: string, code: string, name: string, moderation_status: string, message: string}>}
 */
export async function rejectMetric(metricId, reason = null) {
  const body = reason ? { action: 'reject', reason } : { action: 'reject' }
  const response = await api.post(`/admin/metrics/${metricId}/reject`, body)
  return response.data
}

export default {
  startMetricGeneration,
  getGenerationStatus,
  pollGenerationStatus,
  getPendingMetrics,
  approveMetric,
  rejectMetric,
}
