<template>
  <el-container class="app-layout">
    <el-header class="app-header">
      <div class="header-left">
        <div class="logo">
          <span class="logo-icon">ЦМ</span>
          <span class="logo-text">Цифровая модель УК</span>
        </div>
      </div>

      <div class="header-right">
        <el-menu
          mode="horizontal"
          :default-active="activeRoute"
          :ellipsis="false"
          class="main-menu"
          @select="handleMenuSelect"
        >
          <el-menu-item index="/participants">
            <el-icon><User /></el-icon>
            <span>Участники</span>
          </el-menu-item>

          <el-sub-menu
            v-if="authStore.isAdmin"
            index="admin"
          >
            <template #title>
              <el-icon><Setting /></el-icon>
              <span>Админ</span>
            </template>
            <el-menu-item index="/admin/users">
              Пользователи
            </el-menu-item>
            <el-menu-item index="/admin/weights">
              Весовые таблицы
            </el-menu-item>
            <el-menu-item index="/admin/competencies">
              Словарь компетенций
            </el-menu-item>
            <el-menu-item index="/admin/metric-generate">
              AI Генерация
            </el-menu-item>
            <el-menu-item index="/admin/audit-log">
              Журнал аудита
            </el-menu-item>
          </el-sub-menu>
        </el-menu>

        <el-dropdown @command="handleUserCommand">
          <span class="user-dropdown">
            <el-icon><UserFilled /></el-icon>
            <span>{{ displayName }}</span>
            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile">
                <el-icon><User /></el-icon>
                Профиль
              </el-dropdown-item>
              <el-dropdown-item command="settings">
                <el-icon><Setting /></el-icon>
                Настройки
              </el-dropdown-item>
              <el-dropdown-item
                divided
                command="logout"
              >
                <el-icon><SwitchButton /></el-icon>
                Выход
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-header>

    <el-main class="app-main">
      <slot />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, UserFilled, Setting, ArrowDown, SwitchButton } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const activeRoute = computed(() => route.path)
const displayName = computed(() => authStore.user?.full_name || authStore.user?.email)

const handleMenuSelect = (index) => {
  router.push(index)
}

const handleUserCommand = async (command) => {
  if (command === 'profile') {
    router.push('/profile')
  } else if (command === 'settings') {
    router.push('/settings')
  } else if (command === 'logout') {
    try {
      await authStore.logout()
      ElMessage.success('Выход выполнен')
      router.push('/login')
    } catch (error) {
      ElMessage.error('Ошибка выхода')
    }
  }
}
</script>

<style scoped>
.app-layout {
  min-height: 100vh;
}

.app-header {
  background-color: var(--color-bg-overlay);
  border-bottom: 1px solid var(--color-border-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  box-shadow: var(--shadow-sm);
}

.header-left {
  display: flex;
  align-items: center;
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-icon {
  width: 36px;
  height: 36px;
  background-color: var(--color-primary);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-weight: 600;
  font-size: 14px;
}

.logo-text {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-primary);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.main-menu {
  border-bottom: none;
}

.user-dropdown {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.user-dropdown:hover {
  background-color: var(--color-bg-hover);
}

.app-main {
  background-color: var(--color-bg-page);
  padding: 20px;
}

@media (max-width: 768px) {
  .logo-text {
    display: none;
  }

  .header-right {
    gap: 10px;
  }
}
</style>
