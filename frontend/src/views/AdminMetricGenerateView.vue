<template>
  <app-layout>
    <div class="metric-generate-view">
      <el-card class="header-card">
        <div class="header-content">
          <div>
            <h1>AI Генерация метрик</h1>
            <p>Автоматическое извлечение метрик из PDF-документов с помощью ИИ</p>
          </div>
        </div>
      </el-card>

      <!-- Upload Section -->
      <el-card class="upload-card">
        <h3>Загрузка документа</h3>
        <el-upload
          ref="uploadRef"
          class="upload-area"
          drag
          :auto-upload="false"
          :limit="1"
          :on-change="handleFileChange"
          :on-remove="handleFileRemove"
          accept=".pdf,.docx"
        >
          <el-icon class="el-icon--upload">
            <upload-filled />
          </el-icon>
          <div class="el-upload__text">
            Перетащите файл сюда или <em>нажмите для выбора</em>
          </div>
          <template #tip>
            <div class="el-upload__tip">
              Поддерживаемые форматы: PDF (рекомендуется), DOCX
            </div>
          </template>
        </el-upload>

        <div
          v-if="selectedFile"
          class="upload-actions"
        >
          <el-button
            type="primary"
            size="large"
            :loading="isProcessing"
            :disabled="!selectedFile || isProcessing"
            @click="startGeneration"
          >
            <el-icon v-if="!isProcessing">
              <magic-stick />
            </el-icon>
            {{ isProcessing ? 'Обработка...' : 'Запустить генерацию' }}
          </el-button>
        </div>
      </el-card>

      <!-- Progress Section -->
      <el-card
        v-if="taskId"
        class="progress-card"
      >
        <h3>Прогресс обработки</h3>
        <div class="progress-content">
          <el-progress
            :percentage="progress"
            :status="progressStatus"
            :stroke-width="20"
            striped
            striped-flow
          />
          <p class="progress-step">
            {{ currentStep || 'Ожидание...' }}
          </p>
          <div
            v-if="totalPages"
            class="progress-stats"
          >
            <el-tag>Страниц: {{ processedPages || 0 }}/{{ totalPages }}</el-tag>
            <el-tag
              v-if="metricsFound"
              type="success"
            >
              Найдено метрик: {{ metricsFound }}
            </el-tag>
          </div>
          <el-alert
            v-if="error"
            :title="error"
            type="error"
            show-icon
            :closable="false"
          />
          <el-result
            v-if="taskStatus === 'completed'"
            icon="success"
            title="Генерация завершена"
            :sub-title="`Создано: ${result?.metrics_created || 0}, Сопоставлено: ${result?.metrics_matched || 0}`"
          />
        </div>
      </el-card>

      <!-- Pending Metrics Section -->
      <el-card class="pending-card">
        <template #header>
          <div class="card-header">
            <h3>Метрики на модерации</h3>
            <el-button
              size="small"
              :loading="loadingPending"
              @click="loadPendingMetrics"
            >
              <el-icon><refresh-right /></el-icon>
              Обновить
            </el-button>
          </div>
        </template>

        <el-table
          v-loading="loadingPending"
          :data="pendingMetrics"
          stripe
          style="width: 100%"
        >
          <el-table-column
            label="Название"
            prop="name"
            min-width="200"
          >
            <template #default="{ row }">
              <div class="metric-name">
                <strong>{{ row.name }}</strong>
                <el-tag
                  v-if="row.category_name"
                  size="small"
                  type="info"
                >
                  {{ row.category_name }}
                </el-tag>
              </div>
              <p
                v-if="row.description"
                class="metric-description"
              >
                {{ row.description }}
              </p>
            </template>
          </el-table-column>

          <el-table-column
            label="Обоснование"
            min-width="250"
          >
            <template #default="{ row }">
              <div
                v-if="row.ai_rationale"
                class="rationale"
              >
                <div
                  v-if="row.ai_rationale.quotes?.length"
                  class="quotes"
                >
                  <el-text
                    type="info"
                    size="small"
                  >
                    Цитаты:
                  </el-text>
                  <ul>
                    <li
                      v-for="(quote, i) in row.ai_rationale.quotes.slice(0, 2)"
                      :key="i"
                    >
                      "{{ quote }}"
                    </li>
                  </ul>
                </div>
                <el-tag
                  v-if="row.ai_rationale.page_numbers?.length"
                  size="small"
                  type="info"
                >
                  Стр. {{ row.ai_rationale.page_numbers.join(', ') }}
                </el-tag>
              </div>
              <el-text
                v-else
                type="info"
                size="small"
              >
                Нет данных
              </el-text>
            </template>
          </el-table-column>

          <el-table-column
            label="Действия"
            width="200"
            fixed="right"
          >
            <template #default="{ row }">
              <el-button-group>
                <el-button
                  type="success"
                  size="small"
                  :loading="moderatingId === row.id"
                  @click="handleApprove(row)"
                >
                  <el-icon><check /></el-icon>
                  Одобрить
                </el-button>
                <el-button
                  type="danger"
                  size="small"
                  :loading="moderatingId === row.id"
                  @click="handleReject(row)"
                >
                  <el-icon><close /></el-icon>
                  Отклонить
                </el-button>
              </el-button-group>
            </template>
          </el-table-column>
        </el-table>

        <div
          v-if="pendingTotal > pendingMetrics.length"
          class="load-more"
        >
          <el-button @click="loadMorePending">
            Загрузить ещё
          </el-button>
        </div>

        <el-empty
          v-if="!loadingPending && pendingMetrics.length === 0"
          description="Нет метрик на модерации"
        />
      </el-card>
    </div>
  </app-layout>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  UploadFilled,
  MagicStick,
  RefreshRight,
  Check,
  Close,
} from '@element-plus/icons-vue'
import AppLayout from '../components/AppLayout.vue'
import {
  startMetricGeneration,
  getGenerationStatus,
  getPendingMetrics,
  approveMetric,
  rejectMetric,
} from '../api/metricGeneration.js'

// Upload state
const uploadRef = ref(null)
const selectedFile = ref(null)

// Processing state
const taskId = ref(null)
const taskStatus = ref(null)
const progress = ref(0)
const currentStep = ref('')
const totalPages = ref(null)
const processedPages = ref(null)
const metricsFound = ref(null)
const error = ref(null)
const result = ref(null)
const isProcessing = ref(false)
let pollInterval = null

// Pending metrics state
const pendingMetrics = ref([])
const pendingTotal = ref(0)
const pendingOffset = ref(0)
const loadingPending = ref(false)
const moderatingId = ref(null)

// Computed
const progressStatus = computed(() => {
  if (taskStatus.value === 'completed') return 'success'
  if (taskStatus.value === 'failed') return 'exception'
  return ''
})

// Methods
function handleFileChange(file) {
  selectedFile.value = file.raw
}

function handleFileRemove() {
  selectedFile.value = null
}

async function startGeneration() {
  if (!selectedFile.value) return

  try {
    isProcessing.value = true
    error.value = null
    result.value = null

    const response = await startMetricGeneration(selectedFile.value)
    taskId.value = response.task_id

    ElMessage.success('Обработка запущена')

    // Start polling
    startPolling()
  } catch (err) {
    console.error('Failed to start generation:', err)
    ElMessage.error(err.response?.data?.detail || 'Ошибка запуска генерации')
    isProcessing.value = false
  }
}

function startPolling() {
  if (pollInterval) clearInterval(pollInterval)

  pollInterval = setInterval(async () => {
    try {
      const status = await getGenerationStatus(taskId.value)

      taskStatus.value = status.status
      progress.value = status.progress || 0
      currentStep.value = status.current_step
      totalPages.value = status.total_pages
      processedPages.value = status.processed_pages
      metricsFound.value = status.metrics_found

      if (status.status === 'completed') {
        result.value = status.result
        isProcessing.value = false
        clearInterval(pollInterval)
        ElMessage.success('Генерация завершена!')
        loadPendingMetrics()
      } else if (status.status === 'failed') {
        error.value = status.error || 'Неизвестная ошибка'
        isProcessing.value = false
        clearInterval(pollInterval)
        ElMessage.error('Генерация не удалась')
      }
    } catch (err) {
      console.error('Polling error:', err)
    }
  }, 2000)
}

async function loadPendingMetrics() {
  try {
    loadingPending.value = true
    pendingOffset.value = 0
    const response = await getPendingMetrics({ limit: 20, offset: 0 })
    pendingMetrics.value = response.items
    pendingTotal.value = response.total
  } catch (err) {
    console.error('Failed to load pending metrics:', err)
    ElMessage.error('Ошибка загрузки метрик')
  } finally {
    loadingPending.value = false
  }
}

async function loadMorePending() {
  try {
    loadingPending.value = true
    pendingOffset.value += 20
    const response = await getPendingMetrics({ limit: 20, offset: pendingOffset.value })
    pendingMetrics.value.push(...response.items)
  } catch (err) {
    console.error('Failed to load more:', err)
  } finally {
    loadingPending.value = false
  }
}

async function handleApprove(metric) {
  try {
    moderatingId.value = metric.id
    await approveMetric(metric.id)
    ElMessage.success(`Метрика "${metric.name}" одобрена`)
    pendingMetrics.value = pendingMetrics.value.filter(m => m.id !== metric.id)
    pendingTotal.value--
  } catch (err) {
    console.error('Failed to approve:', err)
    ElMessage.error(err.response?.data?.detail || 'Ошибка одобрения')
  } finally {
    moderatingId.value = null
  }
}

async function handleReject(metric) {
  try {
    const { value: reason } = await ElMessageBox.prompt(
      'Укажите причину отклонения (опционально)',
      'Отклонение метрики',
      {
        confirmButtonText: 'Отклонить',
        cancelButtonText: 'Отмена',
        inputPlaceholder: 'Причина...',
      }
    )

    moderatingId.value = metric.id
    await rejectMetric(metric.id, reason || null)
    ElMessage.warning(`Метрика "${metric.name}" отклонена`)
    pendingMetrics.value = pendingMetrics.value.filter(m => m.id !== metric.id)
    pendingTotal.value--
  } catch (err) {
    if (err === 'cancel') return
    console.error('Failed to reject:', err)
    ElMessage.error(err.response?.data?.detail || 'Ошибка отклонения')
  } finally {
    moderatingId.value = null
  }
}

// Lifecycle
onMounted(() => {
  loadPendingMetrics()
})
</script>

<style scoped>
.metric-generate-view {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.header-card {
  margin-bottom: 20px;
}

.header-content h1 {
  margin: 0 0 8px 0;
  font-size: 24px;
}

.header-content p {
  margin: 0;
  color: var(--el-text-color-secondary);
}

.upload-card,
.progress-card,
.pending-card {
  margin-bottom: 20px;
}

.upload-card h3,
.progress-card h3 {
  margin: 0 0 16px 0;
  font-size: 18px;
}

.upload-area {
  width: 100%;
}

.upload-actions {
  margin-top: 16px;
  text-align: center;
}

.progress-content {
  text-align: center;
}

.progress-step {
  margin: 16px 0;
  color: var(--el-text-color-secondary);
}

.progress-stats {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-top: 12px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header h3 {
  margin: 0;
  font-size: 18px;
}

.metric-name {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.metric-description {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.rationale {
  font-size: 12px;
}

.rationale .quotes {
  margin-bottom: 8px;
}

.rationale .quotes ul {
  margin: 4px 0;
  padding-left: 16px;
}

.rationale .quotes li {
  color: var(--el-text-color-secondary);
  font-style: italic;
}

.load-more {
  margin-top: 16px;
  text-align: center;
}
</style>
