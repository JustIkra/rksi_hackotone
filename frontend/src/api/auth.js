/**
 * Auth API endpoints
 */

import apiClient from './client'

export const authApi = {
  /**
   * Регистрация нового пользователя
   * @param {string} email
   * @param {string} password
   * @param {string|null} fullName - ФИО (необязательно)
   */
  async register(email, password, fullName = null) {
    const payload = { email, password }
    if (fullName) {
      payload.full_name = fullName
    }
    const response = await apiClient.post('/auth/register', payload)
    return response.data
  },

  /**
   * Вход в систему
   * @param {string} email
   * @param {string} password
   */
  async login(email, password) {
    const response = await apiClient.post('/auth/login', { email, password })
    return response.data
  },

  /**
   * Выход из системы
   */
  async logout() {
    const response = await apiClient.post('/auth/logout')
    return response.data
  },

  /**
   * Получить текущего пользователя
   */
  async getMe() {
    const response = await apiClient.get('/auth/me')
    return response.data
  },

  /**
   * Проверить, что пользователь активен
   */
  async checkActive() {
    const response = await apiClient.get('/auth/me/check-active')
    return response.data
  },

  /**
   * Обновить профиль (ФИО)
   * @param {string} fullName
   */
  async updateProfile(fullName) {
    const response = await apiClient.put('/auth/me/profile', { full_name: fullName })
    return response.data
  },

  /**
   * Сменить пароль
   * @param {string} currentPassword
   * @param {string} newPassword
   */
  async changePassword(currentPassword, newPassword) {
    const response = await apiClient.post('/auth/me/change-password', {
      current_password: currentPassword,
      new_password: newPassword
    })
    return response.data
  }
}
