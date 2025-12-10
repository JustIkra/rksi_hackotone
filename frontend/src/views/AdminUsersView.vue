<template>
  <app-layout>
    <div class="admin-users-view">
      <el-card class="header-card">
        <h1>Управление пользователями</h1>
        <p>Одобрение новых пользователей, назначение админов и удаление учётных записей</p>
      </el-card>

      <el-card
        v-loading="adminStore.loading"
        class="users-card"
      >
        <h3>Ожидают одобрения ({{ adminStore.pendingUsers.length }})</h3>

        <el-empty
          v-if="adminStore.pendingUsers.length === 0"
          description="Нет пользователей, ожидающих одобрения"
        />

        <el-table
          v-else
          :data="adminStore.pendingUsers"
          stripe
        >
          <el-table-column
            prop="email"
            label="Email"
            min-width="250"
          />
          <el-table-column
            label="Статус"
            width="140"
          >
            <template #default="{ row }">
              <el-tag :type="getStatusTagType(row.status)">
                {{ getStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="created_at"
            label="Дата регистрации"
            width="180"
          >
            <template #default="{ row }">
              {{ new Date(row.created_at).toLocaleDateString('ru-RU') }}
            </template>
          </el-table-column>
          <el-table-column
            label="Действия"
            width="160"
            align="center"
          >
            <template #default="{ row }">
              <div class="actions-column">
                <el-button
                  type="success"
                  @click="handleApprove(row)"
                >
                  Одобрить
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card
        v-loading="adminStore.loading"
        class="users-card"
      >
        <h3>Все пользователи ({{ allUsers.length }})</h3>

        <el-empty
          v-if="allUsers.length === 0"
          description="Пользователи не найдены"
        />

        <el-table
          v-else
          :data="allUsers"
          stripe
        >
          <el-table-column
            prop="email"
            label="Email"
            min-width="250"
          />
          <el-table-column
            label="Роль"
            width="150"
          >
            <template #default="{ row }">
              <el-tag :type="getRoleTagType(row.role)">
                {{ getRoleLabel(row.role) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            label="Статус"
            width="140"
          >
            <template #default="{ row }">
              <el-tag :type="getStatusTagType(row.status)">
                {{ getStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="created_at"
            label="Дата регистрации"
            width="180"
          >
            <template #default="{ row }">
              {{ new Date(row.created_at).toLocaleDateString('ru-RU') }}
            </template>
          </el-table-column>
          <el-table-column
            label="Действия"
            width="160"
            align="center"
          >
            <template #default="{ row }">
              <div
                v-if="row.id === authStore.user?.id"
                class="actions-column"
              >
                <el-tag type="info">
                  Это вы
                </el-tag>
              </div>
              <div
                v-else
                class="actions-column"
              >
                <el-button
                  v-if="row.role !== 'ADMIN'"
                  type="warning"
                  @click="handleMakeAdmin(row)"
                >
                  В админы
                </el-button>
                <el-button
                  v-if="row.role === 'ADMIN'"
                  type="info"
                  @click="handleRevokeAdmin(row)"
                >
                  Снять админа
                </el-button>
                <el-button
                  type="danger"
                  @click="handleDelete(row)"
                >
                  Удалить
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>
  </app-layout>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/components/AppLayout.vue'
import { useAdminStore, useAuthStore } from '@/stores'
import { getRoleLabel, getRoleTagType, getStatusLabel, getStatusTagType } from '@/utils/labels'

const adminStore = useAdminStore()
const authStore = useAuthStore()

const allUsers = computed(() => adminStore.users)

const handleApprove = async (user) => {
  try {
    await adminStore.approveUser(user.id)
    ElMessage.success(`Пользователь ${user.email} одобрен`)
  } catch (error) {
    ElMessage.error(adminStore.error || 'Ошибка одобрения пользователя')
  }
}

const handleMakeAdmin = async (user) => {
  try {
    await adminStore.makeAdmin(user.id)
    ElMessage.success(`Пользователь ${user.email} назначен администратором`)
  } catch (error) {
    ElMessage.error(adminStore.error || 'Ошибка назначения прав администратора')
  }
}

const handleRevokeAdmin = async (user) => {
  try {
    await adminStore.revokeAdmin(user.id)
    ElMessage.success(`Права администратора сняты с ${user.email}`)
  } catch (error) {
    ElMessage.error(adminStore.error || 'Ошибка снятия прав администратора')
  }
}

const handleDelete = async (user) => {
  if (user.id === authStore.user?.id) {
    ElMessage.error('Нельзя удалить собственную учётную запись администратора')
    return
  }

  try {
    await ElMessageBox.confirm(
      `Вы уверены, что хотите удалить пользователя ${user.email}?`,
      'Подтверждение удаления',
      {
        confirmButtonText: 'Удалить',
        cancelButtonText: 'Отмена',
        type: 'warning',
        confirmButtonClass: 'el-button--danger'
      }
    )

    await adminStore.deleteUser(user.id)
    ElMessage.success(`Пользователь ${user.email} удалён`)
  } catch (error) {
    if (error === 'cancel') {
      return
    }
    ElMessage.error(adminStore.error || 'Ошибка удаления пользователя')
  }
}

onMounted(async () => {
  try {
    await adminStore.fetchPendingUsers()
    await adminStore.fetchAllUsers()
  } catch (error) {
    ElMessage.error(adminStore.error || 'Ошибка загрузки пользователей')
  }
})
</script>

<style scoped>
.admin-users-view {
  max-width: 1200px;
  margin: 0 auto;
}

.header-card {
  margin-bottom: 20px;
}

.header-card h1 {
  margin: 0 0 8px 0;
  font-size: 24px;
  color: var(--color-text-primary);
}

.header-card p {
  margin: 0;
  color: var(--color-text-regular);
}

.users-card h3 {
  margin: 0 0 20px 0;
  font-size: 18px;
  color: var(--color-text-primary);
}

.users-card {
  margin-bottom: 20px;
}

.actions-column {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 0;
}

.actions-column .el-button {
  width: 100%;
  margin: 0;
}
</style>
