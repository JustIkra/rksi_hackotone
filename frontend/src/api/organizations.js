/**
 * Organizations API endpoints
 */

import apiClient from './client'

export const organizationsApi = {
  // --- Organizations ---

  async create(data) {
    const response = await apiClient.post('/organizations', data)
    return response.data
  },

  async search(params = {}) {
    const response = await apiClient.get('/organizations', { params })
    return response.data
  },

  async getById(orgId) {
    const response = await apiClient.get(`/organizations/${orgId}`)
    return response.data
  },

  async update(orgId, data) {
    const response = await apiClient.put(`/organizations/${orgId}`, data)
    return response.data
  },

  async delete(orgId) {
    const response = await apiClient.delete(`/organizations/${orgId}`)
    return response.data
  },

  // --- Departments ---

  async createDepartment(orgId, data) {
    const response = await apiClient.post(`/organizations/${orgId}/departments`, data)
    return response.data
  },

  async listDepartments(orgId) {
    const response = await apiClient.get(`/organizations/${orgId}/departments`)
    return response.data
  },

  async updateDepartment(orgId, deptId, data) {
    const response = await apiClient.put(`/organizations/${orgId}/departments/${deptId}`, data)
    return response.data
  },

  async deleteDepartment(orgId, deptId) {
    const response = await apiClient.delete(`/organizations/${orgId}/departments/${deptId}`)
    return response.data
  },

  // --- Participants in department ---

  async listDepartmentParticipants(orgId, deptId) {
    const response = await apiClient.get(`/organizations/${orgId}/departments/${deptId}/participants`)
    return response.data
  },

  async attachParticipants(orgId, deptId, participantIds) {
    const response = await apiClient.post(
      `/organizations/${orgId}/departments/${deptId}/participants`,
      { participant_ids: participantIds }
    )
    return response.data
  },

  async detachParticipant(orgId, deptId, participantId) {
    const response = await apiClient.delete(
      `/organizations/${orgId}/departments/${deptId}/participants`,
      { data: { participant_id: participantId } }
    )
    return response.data
  },

  // --- Weight table ---

  async attachWeightTable(orgId, deptId, weightTableId) {
    const response = await apiClient.put(
      `/organizations/${orgId}/departments/${deptId}/weight-table`,
      { weight_table_id: weightTableId }
    )
    return response.data
  },

  async listDepartmentParticipantsWithScores(orgId, deptId) {
    const response = await apiClient.get(
      `/organizations/${orgId}/departments/${deptId}/participants/scores`
    )
    return response.data
  },

  async calculateDepartmentScores(orgId, deptId) {
    const response = await apiClient.post(
      `/organizations/${orgId}/departments/${deptId}/calculate-scores`
    )
    return response.data
  }
}
