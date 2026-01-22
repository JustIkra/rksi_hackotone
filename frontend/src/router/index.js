/**
 * Vue Router configuration
 */

import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/LandingView.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('@/views/RegisterView.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/participants',
      name: 'participants',
      component: () => import('@/views/ParticipantsView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/participants/:id',
      name: 'participant-detail',
      component: () => import('@/views/ParticipantDetailView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/admin/users',
      name: 'admin-users',
      component: () => import('@/views/AdminUsersView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true }
    },
    {
      path: '/admin/weights',
      name: 'admin-weights',
      component: () => import('@/views/AdminWeightsView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true }
    },
    {
      path: '/admin/competencies',
      name: 'admin-competencies',
      component: () => import('@/views/AdminCompetenciesView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true }
    },
    {
      path: '/admin/audit-log',
      name: 'admin-audit-log',
      component: () => import('@/views/AdminAuditLogView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true }
    },
    {
      path: '/admin/metric-generate',
      name: 'admin-metric-generate',
      component: () => import('@/views/AdminMetricGenerateView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true }
    },
    {
      path: '/profile',
      name: 'profile',
      component: () => import('@/views/ProfileView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
      meta: { requiresAuth: true }
    }
  ]
})

// Navigation guards
router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  // Проверка авторизации
  if (to.meta.requiresAuth) {
    if (!authStore.isAuthenticated) {
      try {
        await authStore.fetchCurrentUser()
      } catch (error) {
        return next({ name: 'login', query: { redirect: to.fullPath } })
      }
    }

    // Проверка активности пользователя
    if (!authStore.isActive) {
      return next({ name: 'login', query: { message: 'pending' } })
    }

    // Проверка прав админа
    if (to.meta.requiresAdmin && !authStore.isAdmin) {
      return next({ name: 'participants' })
    }
  }

  // Если пользователь авторизован и пытается зайти на /login или /register или landing
  if ((to.name === 'login' || to.name === 'register' || to.name === 'home') && authStore.isAuthenticated) {
    return next({ name: 'participants' })
  }

  next()
})

export default router
