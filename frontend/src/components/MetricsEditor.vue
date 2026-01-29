<template>
  <el-card class="metrics-editor">
    <template #header>
      <div class="card-header">
        <div class="card-header-left">
          <span>Метрики отчёта</span>
          <el-tag
            v-if="reportStatus === 'PROCESSING'"
            type="warning"
            size="small"
            class="status-tag"
          >
            <el-icon class="is-loading">
              <Loading />
            </el-icon>
            Извлечение...
          </el-tag>
          <el-tag
            v-else-if="reportStatus === 'EXTRACTED'"
            type="success"
            size="small"
            class="status-tag"
          >
            Извлечено
          </el-tag>
        </div>
        <div class="card-header-actions">
          <el-button
            v-if="!isEditing"
            size="small"
            :loading="loading"
            @click="refreshMetrics"
          >
            <el-icon><Refresh /></el-icon>
            Обновить
          </el-button>
          <el-button
            v-if="!isEditing"
            type="primary"
            size="small"
            @click="startEditing"
          >
            Редактировать
          </el-button>
          <template v-else>
            <el-button
              size="small"
              @click="cancelEditing"
            >
              Отмена
            </el-button>
            <el-button
              type="primary"
              size="small"
              :loading="saving"
              @click="saveMetrics"
            >
              Сохранить
            </el-button>
          </template>
        </div>
      </div>
    </template>

    <el-alert
      v-if="error"
      type="error"
      :title="error"
      closable
      style="margin-bottom: 16px;"
      @close="error = null"
    />

    <el-alert
      v-if="props.reportExtractWarning && props.reportStatus === 'EXTRACTED'"
      type="warning"
      :title="props.reportExtractWarning"
      :closable="false"
      style="margin-bottom: 16px;"
    />

    <el-alert
      v-if="!metrics || metrics.length === 0"
      type="info"
      :closable="false"
      style="margin-bottom: 16px;"
    >
      Метрики для этого отчёта ещё не извлечены. Вы можете ввести их вручную.
    </el-alert>

    <el-tabs
      v-model="activeTab"
      type="card"
    >
      <el-tab-pane
        label="Метрики"
        name="metrics"
      >
        <div class="metrics-filter">
          <el-switch
            v-model="showAllMetrics"
            active-text="Показать все метрики"
            inactive-text="Только заполненные"
          />
          <div class="metrics-stats">
            <el-tag
              type="success"
              size="small"
            >
              Заполнено: {{ filledCount }}
            </el-tag>
            <el-tag
              type="info"
              size="small"
            >
              Не заполнено: {{ missingCount }}
            </el-tag>
            <span class="metrics-count">
              Показано: {{ filteredMetrics.length }} из {{ availableMetrics.length }}
            </span>
          </div>
        </div>

        <el-form
          ref="formRef"
          :model="formData"
          label-position="top"
          :disabled="!isEditing"
        >
          <el-row :gutter="20">
            <el-col
              v-for="metricDef in filteredMetrics"
              :key="metricDef.id"
              :xs="24"
              :sm="12"
              :md="8"
              :lg="6"
            >
              <el-form-item
                :label="formatMetricLabel(metricDef)"
                :prop="`metrics.${metricDef.id}`"
              >
                <MetricInput
                  v-model="formData.metrics[metricDef.id]"
                  :min="metricDef.min_value || 1"
                  :max="metricDef.max_value || 10"
                  :precision="1"
                  :step="0.1"
                  :disabled="!isEditing"
                  :show-controls="true"
                  placeholder="Введите значение (например: 7,5)"
                />
                <div
                  v-if="metricDef.description"
                  class="metric-description"
                >
                  {{ metricDef.description }}
                </div>
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>

        <div
          v-if="metrics && metrics.length > 0"
          class="metrics-info"
        >
          <el-divider />
          <div class="info-row">
            <span class="info-label">Источник данных:</span>
            <el-tag
              v-for="source in uniqueSources"
              :key="source"
              :type="getSourceType(source)"
              size="small"
              style="margin-left: 8px;"
            >
              {{ getSourceLabel(source) }}
            </el-tag>
          </div>
          <div
            v-if="lastUpdated"
            class="info-row"
          >
            <span class="info-label">Последнее обновление:</span>
            <span>{{ formatDate(lastUpdated) }}</span>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </el-card>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Loading,
  Refresh
} from '@element-plus/icons-vue'
import MetricInput from './MetricInput.vue'
import { metricsApi } from '@/api'
import { parseNumber, formatForApi } from '@/utils/numberFormat'
import { formatMetricLabel } from '@/utils/metricNames'
import { formatDateLong } from '@/utils/dateFormat'

const props = defineProps({
  reportId: {
    type: String,
    required: true
  },
  reportStatus: {
    type: String,
    default: null
  },
  reportExtractWarning: {
    type: String,
    default: null
  }
})

const emit = defineEmits(['metrics-updated'])

// State
const loading = ref(false)
const saving = ref(false)
const isEditing = ref(false)
const error = ref(null)
const showAllMetrics = ref(false)

// Counters for filled/missing metrics from template
const filledCount = ref(0)
const missingCount = ref(0)

const availableMetrics = ref([])
const metrics = ref([])
const formData = ref({ metrics: {} })
const originalData = ref({})

// Tab state
const activeTab = ref('metrics')

// Polling state
const pollingInterval = ref(null)

// Computed
// Фильтруем метрики: показываем только те, у которых есть реальное значение
// (скрываем пустые метрики без маппинга и с нулевыми значениями)
// Либо показываем все, если включен режим "Показать все метрики"
const filteredMetrics = computed(() => {
  if (!availableMetrics.value || availableMetrics.value.length === 0) {
    return []
  }

  // Если включен режим "показать все" - возвращаем все метрики
  if (showAllMetrics.value) {
    return availableMetrics.value
  }

  // Иначе показываем только метрики с реальными значениями
  // Собираем ID метрик с реальными (не нулевыми) значениями
  const extractedMetricIds = new Set(
    metrics.value
      .filter(m => {
        const val = parseFloat(String(m.value).replace(',', '.'))
        return !isNaN(val) && val > 0
      })
      .map(m => m.metric_def_id)
  )

  // Показываем только метрики с реальными извлечёнными значениями или заполненными вручную
  return availableMetrics.value.filter(metricDef => {
    const hasExtractedValue = extractedMetricIds.has(metricDef.id)
    const formValue = formData.value.metrics[metricDef.id]
    const hasFormValue = formValue !== undefined &&
                         formValue !== null &&
                         formValue !== '' &&
                         parseFloat(String(formValue).replace(',', '.')) > 0
    return hasExtractedValue || hasFormValue
  })
})

const uniqueSources = computed(() => {
  if (!metrics.value || metrics.value.length === 0) return []
  return [...new Set(metrics.value.map(m => m.source))]
})

const lastUpdated = computed(() => {
  if (!metrics.value || metrics.value.length === 0) return null
  // Найти самую свежую дату обновления среди всех метрик
  const dates = metrics.value
    .map(m => m.updated_at || m.created_at)
    .filter(Boolean)
    .map(d => new Date(d))
  if (dates.length === 0) return null
  return new Date(Math.max(...dates))
})

// Methods
const loadMetrics = async () => {
  loading.value = true
  error.value = null
  try {
    // Use template endpoint to get ALL metrics including empty ones
    const response = await metricsApi.getMetricTemplate(props.reportId)

    // Store template metadata
    filledCount.value = response.filled_count || 0
    missingCount.value = response.missing_count || 0

    // Extract metrics from template items
    const templateItems = response.items || []

    // Build metrics array from template (for backward compatibility with existing code)
    metrics.value = templateItems
      .filter(item => item.value !== null)
      .map(item => ({
        metric_def_id: item.metric_def.id,
        value: item.value,
        source: item.source,
        confidence: item.confidence,
        notes: item.notes,
        updated_at: item.updated_at
      }))

    // Build availableMetrics from template
    availableMetrics.value = templateItems.map(item => ({
      id: item.metric_def.id,
      code: item.metric_def.code,
      name: item.metric_def.name,
      name_ru: item.metric_def.name_ru,
      unit: item.metric_def.unit,
      min_value: item.metric_def.min_value,
      max_value: item.metric_def.max_value,
      description: item.metric_def.description
    }))

    // Populate formData with all values (including null for empty metrics)
    formData.value.metrics = {}
    templateItems.forEach(item => {
      const metricDefId = item.metric_def.id
      if (item.value !== null) {
        formData.value.metrics[metricDefId] = parseNumber(item.value)
      } else {
        // Initialize empty metrics with null
        formData.value.metrics[metricDefId] = null
      }
    })

    // Сохраняем оригинальные данные для отмены
    originalData.value = JSON.parse(JSON.stringify(formData.value.metrics))
  } catch (err) {
    console.error('Failed to load metrics:', err)
    error.value = 'Не удалось загрузить метрики'
  } finally {
    loading.value = false
  }
}

const refreshMetrics = async () => {
  await loadMetrics()
  ElMessage.success('Метрики обновлены')
}

const startPolling = () => {
  if (pollingInterval.value) return
  pollingInterval.value = setInterval(async () => {
    await loadMetrics()
  }, 5000)
}

const stopPolling = () => {
  if (pollingInterval.value) {
    clearInterval(pollingInterval.value)
    pollingInterval.value = null
  }
}

const startEditing = () => {
  isEditing.value = true
  showAllMetrics.value = true // Автоматически показываем все метрики в режиме редактирования
  originalData.value = JSON.parse(JSON.stringify(formData.value.metrics))
}

const cancelEditing = () => {
  formData.value.metrics = JSON.parse(JSON.stringify(originalData.value))
  isEditing.value = false
  error.value = null
}

const saveMetrics = async () => {
  saving.value = true
  error.value = null

  try {
    // Собираем метрики для отправки и для удаления
    const metricsToSave = []
    const metricsToDelete = []

    for (const [metricDefId, value] of Object.entries(formData.value.metrics)) {
      const originalValue = originalData.value[metricDefId]
      const hasOriginalValue = originalValue !== null && originalValue !== undefined && originalValue !== ''

      if (value !== null && value !== undefined && value !== '') {
        // Используем formatForApi для корректной отправки на сервер
        const apiValue = formatForApi(value)
        if (apiValue !== null) {
          metricsToSave.push({
            metric_def_id: metricDefId,
            value: apiValue,
            source: 'MANUAL',
            notes: null
          })
        }
      } else if (hasOriginalValue) {
        // Значение было очищено - нужно удалить метрику
        metricsToDelete.push(metricDefId)
      }
    }

    // Удаляем очищенные метрики параллельно (eliminates sequential requests)
    const deleteResults = await Promise.allSettled(
      metricsToDelete.map(metricDefId =>
        metricsApi.clearExtractedMetric(props.reportId, metricDefId)
      )
    )
    const deletedCount = deleteResults.filter(r =>
      r.status === 'fulfilled' ||
      (r.status === 'rejected' && r.reason?.response?.status === 404)
    ).length

    // Сохраняем заполненные метрики
    if (metricsToSave.length > 0) {
      await metricsApi.bulkCreateExtractedMetrics(props.reportId, metricsToSave)
    }

    // Формируем сообщение об успехе
    const messages = []
    if (metricsToSave.length > 0) {
      messages.push(`сохранено: ${metricsToSave.length}`)
    }
    if (deletedCount > 0) {
      messages.push(`сброшено: ${deletedCount}`)
    }

    if (messages.length === 0) {
      ElMessage.info('Нет изменений для сохранения')
    } else {
      ElMessage.success(`Метрики обновлены (${messages.join(', ')})`)
    }

    isEditing.value = false

    // Перезагружаем метрики
    await loadMetrics()

    emit('metrics-updated')
  } catch (err) {
    console.error('Failed to save metrics:', err)
    // Улучшенная обработка ошибок
    let errorMessage = 'Не удалось сохранить метрики'
    if (err.response?.data?.detail) {
      if (typeof err.response.data.detail === 'string') {
        errorMessage = err.response.data.detail
      } else if (Array.isArray(err.response.data.detail)) {
        errorMessage = err.response.data.detail.map(e => e.msg || e.message).join(', ')
      }
    }
    error.value = errorMessage
    ElMessage.error(errorMessage)
  } finally {
    saving.value = false
  }
}

const getSourceType = (source) => {
  switch (source) {
    case 'OCR': return 'info'
    case 'LLM': return 'warning'
    case 'MANUAL': return 'success'
    default: return ''
  }
}

const getSourceLabel = (source) => {
  switch (source) {
    case 'OCR': return 'OCR'
    case 'LLM': return 'Gemini Vision'
    case 'MANUAL': return 'Ручной ввод'
    default: return source
  }
}

// Используем formatDateLong для развернутого формата даты
const formatDate = formatDateLong

// Lifecycle
onMounted(async () => {
  // loadMetrics() вызывается через watch на reportStatus
  // loadMetricDefs больше не нужен - все данные приходят через template endpoint
})

onUnmounted(() => {
  stopPolling()
})

// Watch для изменения reportId
watch(() => props.reportId, async (newId) => {
  if (newId) {
    await loadMetrics()
  }
})

// Watch для reportStatus - автоматическое обновление при PROCESSING
watch(() => props.reportStatus, async (newStatus, oldStatus) => {
  // При первой инициализации (oldStatus === undefined) всегда загружаем метрики
  if (!oldStatus) {
    await loadMetrics()
  }

  if (newStatus === 'PROCESSING') {
    startPolling()
    // Если переходим в PROCESSING из другого статуса (переизвлечение) - перезагружаем метрики
    if (oldStatus && oldStatus !== 'PROCESSING') {
      await loadMetrics()
    }
  } else {
    stopPolling()
    // Когда извлечение завершено (EXTRACTED), всегда загружаем финальные метрики
    // Это исправляет баг, когда метрики не обновлялись после переизвлечения
    if (newStatus === 'EXTRACTED' && oldStatus && oldStatus !== 'EXTRACTED') {
      await loadMetrics()
    }
  }
}, { immediate: true })
</script>

<style scoped>
.metrics-editor {
  margin-top: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.card-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.metrics-filter {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}

.metrics-stats {
  display: flex;
  align-items: center;
  gap: 8px;
}

.metrics-count {
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.metric-description {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  line-height: 1.4;
}

.metrics-info {
  margin-top: 16px;
}

.info-row {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
  font-size: 14px;
}

.info-label {
  font-weight: 500;
  color: var(--el-text-color-secondary);
  margin-right: 8px;
}
</style>
