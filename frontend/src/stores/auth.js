/**
 * Auth Store - управление аутентификацией
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api'
import { normalizeApiError } from '@/utils/normalizeError'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const loading = ref(false)
  const error = ref(null)

  const isAuthenticated = computed(() => user.value !== null)
  const isAdmin = computed(() => user.value?.role === 'ADMIN')
  const isActive = computed(() => user.value?.status === 'ACTIVE')
  const displayName = computed(() => user.value?.full_name || user.value?.email)

  async function register(email, password, fullName = null) {
    loading.value = true
    error.value = null
    try {
      const data = await authApi.register(email, password, fullName)
      return data
    } catch (err) {
      const normalized = normalizeApiError(err, 'Ошибка регистрации')
      error.value = normalized.message
      err.normalizedError = normalized
      throw err
    } finally {
      loading.value = false
    }
  }

  async function login(email, password) {
    loading.value = true
    error.value = null
    try {
      const data = await authApi.login(email, password)
      user.value = data.user
      return data
    } catch (err) {
      const normalized = normalizeApiError(err, 'Ошибка входа')
      error.value = normalized.message
      err.normalizedError = normalized
      throw err
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    loading.value = true
    error.value = null
    try {
      await authApi.logout()
      user.value = null
    } catch (err) {
      const normalized = normalizeApiError(err, 'Ошибка выхода')
      error.value = normalized.message
      err.normalizedError = normalized
      throw err
    } finally {
      loading.value = false
    }
  }

  async function fetchCurrentUser() {
    loading.value = true
    error.value = null
    try {
      const data = await authApi.getMe()
      user.value = data
      return data
    } catch (err) {
      user.value = null
      const normalized = normalizeApiError(err, 'Ошибка получения пользователя')
      error.value = normalized.message
      err.normalizedError = normalized
      throw err
    } finally {
      loading.value = false
    }
  }

  async function checkActive() {
    loading.value = true
    error.value = null
    try {
      const data = await authApi.checkActive()
      user.value = data
      return data
    } catch (err) {
      const normalized = normalizeApiError(err, 'Пользователь не активен')
      error.value = normalized.message
      err.normalizedError = normalized
      throw err
    } finally {
      loading.value = false
    }
  }

  async function updateProfile(fullName) {
    loading.value = true
    error.value = null
    try {
      const data = await authApi.updateProfile(fullName)
      user.value = data
      return data
    } catch (err) {
      const normalized = normalizeApiError(err, 'Ошибка обновления профиля')
      error.value = normalized.message
      err.normalizedError = normalized
      throw err
    } finally {
      loading.value = false
    }
  }

  async function changePassword(currentPassword, newPassword) {
    loading.value = true
    error.value = null
    try {
      const data = await authApi.changePassword(currentPassword, newPassword)
      return data
    } catch (err) {
      const normalized = normalizeApiError(err, 'Ошибка смены пароля')
      error.value = normalized.message
      err.normalizedError = normalized
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    user,
    loading,
    error,
    isAuthenticated,
    isAdmin,
    isActive,
    displayName,
    register,
    login,
    logout,
    fetchCurrentUser,
    checkActive,
    updateProfile,
    changePassword
  }
})
