/**
 * Metric Categories API endpoints
 */

import apiClient from './client'

export const metricCategoriesApi = {
  /**
   * Get all metric categories
   * @returns {Promise<Array>} List of metric categories
   */
  list: () => apiClient.get('/admin/metric-categories').then(r => r.data),

  /**
   * Create a new metric category
   * @param {Object} data - Category data { name, description }
   * @returns {Promise<Object>} Created category
   */
  create: (data) => apiClient.post('/admin/metric-categories', data).then(r => r.data),

  /**
   * Update an existing metric category
   * @param {string} id - Category UUID
   * @param {Object} data - Updated category data
   * @returns {Promise<Object>} Updated category
   */
  update: (id, data) => apiClient.put(`/admin/metric-categories/${id}`, data).then(r => r.data),

  /**
   * Delete a metric category
   * @param {string} id - Category UUID
   * @returns {Promise<Object>} Deletion result
   */
  delete: (id) => apiClient.delete(`/admin/metric-categories/${id}`).then(r => r.data),

  /**
   * Reorder a single category to a new position
   * @param {string} categoryId - UUID of category to move
   * @param {number} targetPosition - Target position (0-based index)
   * @returns {Promise<Object>} Updated categories list
   */
  reorder: (categoryId, targetPosition) => apiClient.patch('/admin/metric-categories/reorder', {
    category_id: categoryId,
    target_position: targetPosition
  }).then(r => r.data),
}
