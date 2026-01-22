<template>
  <app-layout>
    <div class="audit-log-view">
      <el-card class="header-card">
        <div class="header-content">
          <div>
            <h1>Журнал аудита</h1>
            <p>История операций с метриками</p>
          </div>
        </div>
      </el-card>

      <!-- Фильтры -->
      <el-card class="filters-card">
        <el-form
          :inline="true"
          :model="filters"
          class="filters-form"
        >
          <el-form-item label="Период">
            <el-date-picker
              v-model="dateRange"
              type="daterange"
              range-separator="—"
              start-placeholder="Начало"
              end-placeholder="Конец"
              format="DD.MM.YYYY"
              value-format="YYYY-MM-DDTHH:mm:ss"
              :shortcuts="dateShortcuts"
              @change="handleDateChange"
            />
          </el-form-item>

          <el-form-item label="Действие">
            <el-select
              v-model="filters.action"
              placeholder="Все действия"
              clearable
              style="width: 200px"
              @change="loadAuditLog"
            >
              <el-option
                v-for="action in actionTypes"
                :key="action"
                :label="getActionLabel(action)"
                :value="action"
              />
            </el-select>
          </el-form-item>

          <el-form-item>
            <el-button
              type="primary"
              @click="loadAuditLog"
            >
              <el-icon><Search /></el-icon>
              Применить
            </el-button>
            <el-button @click="resetFilters">
              Сбросить
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- Таблица -->
      <el-card
        v-loading="loading"
        class="table-card"
      >
        <el-table
          v-if="auditLogs.length > 0"
          :data="auditLogs"
          stripe
          style="width: 100%"
        >
          <el-table-column
            label="Дата и время"
            width="180"
          >
            <template #default="{ row }">
              {{ formatDateTime(row.timestamp) }}
            </template>
          </el-table-column>

          <el-table-column
            label="Пользователь"
            width="200"
          >
            <template #default="{ row }">
              <div v-if="row.user">
                <div class="user-name">{{ row.user.full_name || row.user.email }}</div>
                <div
                  v-if="row.user.full_name"
                  class="user-email"
                >
                  {{ row.user.email }}
                </div>
              </div>
              <span
                v-else
                class="text-muted"
              >Система</span>
            </template>
          </el-table-column>

          <el-table-column
            label="Действие"
            width="150"
          >
            <template #default="{ row }">
              <el-tag :type="getActionTagType(row.action)">
                {{ getActionLabel(row.action) }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column
            label="Коды метрик"
            min-width="250"
          >
            <template #default="{ row }">
              <div class="metric-codes">
                <el-tag
                  v-for="code in row.metric_codes.slice(0, 5)"
                  :key="code"
                  size="small"
                  type="info"
                  class="metric-code-tag"
                >
                  {{ code }}
                </el-tag>
                <el-tag
                  v-if="row.metric_codes.length > 5"
                  size="small"
                  type="info"
                >
                  +{{ row.metric_codes.length - 5 }}
                </el-tag>
              </div>
            </template>
          </el-table-column>

          <el-table-column
            label="Затронуто"
            width="200"
          >
            <template #default="{ row }">
              <div
                v-if="row.affected_counts"
                class="affected-counts"
              >
                <div v-if="row.affected_counts.extracted_metrics">
                  Извлеч. метрик: {{ row.affected_counts.extracted_metrics }}
                </div>
                <div v-if="row.affected_counts.synonyms">
                  Синонимов: {{ row.affected_counts.synonyms }}
                </div>
                <div v-if="row.affected_counts.weight_tables">
                  Весовых таблиц: {{ row.affected_counts.weight_tables }}
                </div>
              </div>
              <span
                v-else
                class="text-muted"
              >—</span>
            </template>
          </el-table-column>
        </el-table>

        <el-empty
          v-else-if="!loading"
          description="Нет записей"
        />

        <!-- Пагинация -->
        <div
          v-if="total > 0"
          class="pagination-wrapper"
        >
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :total="total"
            :page-sizes="[20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            @size-change="handleSizeChange"
            @current-change="handlePageChange"
          />
        </div>
      </el-card>
    </div>
  </app-layout>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import AppLayout from '@/components/AppLayout.vue'
import { adminApi } from '@/api/admin'

// State
const loading = ref(false)
const auditLogs = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(50)
const actionTypes = ref([])

// Filters
const dateRange = ref(null)
const filters = ref({
  start_date: null,
  end_date: null,
  action: null
})

// Date shortcuts
const dateShortcuts = [
  {
    text: 'Сегодня',
    value: () => {
      const today = new Date()
      today.setHours(0, 0, 0, 0)
      const end = new Date()
      end.setHours(23, 59, 59, 999)
      return [today, end]
    }
  },
  {
    text: 'Последние 7 дней',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setDate(start.getDate() - 7)
      return [start, end]
    }
  },
  {
    text: 'Последние 30 дней',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setDate(start.getDate() - 30)
      return [start, end]
    }
  }
]

// Action labels
const actionLabels = {
  bulk_delete: 'Массовое удаление',
  delete: 'Удаление',
  create: 'Создание',
  update: 'Обновление'
}

const getActionLabel = (action) => {
  return actionLabels[action] || action
}

const getActionTagType = (action) => {
  const types = {
    bulk_delete: 'danger',
    delete: 'danger',
    create: 'success',
    update: 'warning'
  }
  return types[action] || 'info'
}

// Date formatting
const formatDateTime = (timestamp) => {
  if (!timestamp) return '—'
  const date = new Date(timestamp)
  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// Handlers
const handleDateChange = (range) => {
  if (range && range.length === 2) {
    filters.value.start_date = range[0]
    filters.value.end_date = range[1]
  } else {
    filters.value.start_date = null
    filters.value.end_date = null
  }
  loadAuditLog()
}

const handleSizeChange = () => {
  currentPage.value = 1
  loadAuditLog()
}

const handlePageChange = () => {
  loadAuditLog()
}

const resetFilters = () => {
  dateRange.value = null
  filters.value = {
    start_date: null,
    end_date: null,
    action: null
  }
  currentPage.value = 1
  loadAuditLog()
}

// API calls
const loadAuditLog = async () => {
  loading.value = true
  try {
    const params = {
      limit: pageSize.value,
      offset: (currentPage.value - 1) * pageSize.value
    }

    if (filters.value.start_date) {
      params.start_date = filters.value.start_date
    }
    if (filters.value.end_date) {
      params.end_date = filters.value.end_date
    }
    if (filters.value.action) {
      params.action = filters.value.action
    }

    const response = await adminApi.getAuditLog(params)
    auditLogs.value = response.items || []
    total.value = response.total || 0
  } catch (err) {
    console.error('Failed to load audit log:', err)
    ElMessage.error('Не удалось загрузить журнал аудита')
  } finally {
    loading.value = false
  }
}

const loadActionTypes = async () => {
  try {
    const response = await adminApi.getAuditActionTypes()
    actionTypes.value = response.actions || []
  } catch (err) {
    console.error('Failed to load action types:', err)
  }
}

// Init
onMounted(async () => {
  await Promise.all([
    loadAuditLog(),
    loadActionTypes()
  ])
})
</script>

<style scoped>
.audit-log-view {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
}

.header-card {
  margin-bottom: 24px;
  border-radius: 12px;
}

.header-content h1 {
  margin: 0 0 8px 0;
  font-size: 28px;
  font-weight: 600;
}

.header-content p {
  margin: 0;
  color: var(--el-text-color-secondary);
}

.filters-card {
  margin-bottom: 24px;
  border-radius: 12px;
}

.filters-form {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.table-card {
  border-radius: 12px;
}

.user-name {
  font-weight: 500;
}

.user-email {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.text-muted {
  color: var(--el-text-color-placeholder);
}

.metric-codes {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.metric-code-tag {
  font-family: monospace;
}

.affected-counts {
  font-size: 12px;
  line-height: 1.6;
}

.pagination-wrapper {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
