<template>
  <app-layout>
    <div class="admin-competencies-view">
      <el-card class="header-card">
        <div class="header-content">
          <div>
            <h1>Словарь компетенций</h1>
            <p>Управление метриками и категориями для оценки профессиональной пригодности</p>
          </div>
          <div class="header-buttons">
            <!-- Embedding stats badge -->
            <el-tooltip
              v-if="embeddingStats"
              :content="`Проиндексировано: ${embeddingStats.total_embeddings}/${embeddingStats.total_approved_metrics} (${embeddingStats.coverage_percent}%)`"
              placement="bottom"
            >
              <el-tag
                :type="embeddingStats.coverage_percent >= 95 ? 'success' : embeddingStats.coverage_percent >= 50 ? 'warning' : 'danger'"
                effect="plain"
                style="margin-right: 8px"
              >
                🔍 {{ embeddingStats.coverage_percent }}%
              </el-tag>
            </el-tooltip>

            <el-button
              size="large"
              :loading="reindexing"
              @click="handleReindexAll"
            >
              <el-icon><RefreshRight /></el-icon>
              Переиндексация
            </el-button>
            <el-button
              size="large"
              @click="handleImport"
            >
              <el-icon><Upload /></el-icon>
              Импорт
            </el-button>
            <el-button
              size="large"
              type="primary"
              @click="handleExport"
            >
              <el-icon><Download /></el-icon>
              Экспорт
            </el-button>
          </div>
        </div>
      </el-card>

      <!-- Поиск по названию -->
      <el-card class="search-card">
        <el-input
          v-model="searchQuery"
          placeholder="Поиск по названию метрики..."
          :prefix-icon="Search"
          size="large"
          clearable
        />
      </el-card>

      <!-- Основное содержимое -->
      <div
        v-loading="loading"
        class="content-container"
      >
        <!-- Error State -->
        <el-result
          v-if="error"
          icon="error"
          title="Ошибка загрузки"
          :sub-title="error"
        >
          <template #extra>
            <el-button
              type="primary"
              @click="loadData"
            >
              <el-icon><RefreshRight /></el-icon>
              Повторить
            </el-button>
          </template>
        </el-result>

        <!-- Main Layout -->
        <div
          v-else
          class="main-layout"
        >
          <!-- Sidebar with categories -->
          <div class="categories-sidebar">
            <div class="sidebar-header">
              <h3>Категории</h3>
              <el-button
                type="primary"
                size="small"
                circle
                @click="showCategoryDialog()"
              >
                <el-icon><Plus /></el-icon>
              </el-button>
            </div>

            <div class="category-list">
              <div
                :class="['category-item', { active: selectedCategoryId === null }]"
                @click="selectedCategoryId = null"
              >
                <el-icon><Menu /></el-icon>
                <span class="category-name">Все метрики</span>
                <el-tag
                  size="small"
                  type="info"
                >
                  {{ allMetrics.length }}
                </el-tag>
              </div>

              <draggable
                v-model="categories"
                item-key="id"
                handle=".drag-handle"
                ghost-class="category-ghost"
                @end="onCategoriesReorder"
              >
                <template #item="{ element: category }">
                  <div
                    :class="['category-item', { active: selectedCategoryId === category.id }]"
                    @click="selectedCategoryId = category.id"
                  >
                    <el-icon class="drag-handle">
                      <Rank />
                    </el-icon>
                    <span class="category-name">{{ category.name }}</span>
                    <el-tag
                      size="small"
                      type="info"
                    >
                      {{ getMetricsCountByCategory(category.id) }}
                    </el-tag>
                    <el-button
                      size="small"
                      circle
                      class="edit-btn"
                      @click.stop="showCategoryDialog(category)"
                    >
                      <el-icon><Edit /></el-icon>
                    </el-button>
                  </div>
                </template>
              </draggable>

              <div
                :class="['category-item', { active: selectedCategoryId === 'uncategorized' }]"
                @click="selectedCategoryId = 'uncategorized'"
              >
                <el-icon><Folder /></el-icon>
                <span class="category-name">Без категории</span>
                <el-tag
                  size="small"
                  type="warning"
                >
                  {{ uncategorizedMetricsCount }}
                </el-tag>
              </div>
            </div>
          </div>

          <!-- Metrics table -->
          <div class="metrics-content">
            <div class="metrics-header">
              <h3>{{ selectedCategoryTitle }}</h3>
              <el-button
                type="primary"
                @click="showMetricDialog()"
              >
                <el-icon><Plus /></el-icon>
                Добавить метрику
              </el-button>
            </div>

            <!-- Bulk actions toolbar -->
            <div
              v-if="selectedMetrics.length > 0"
              class="bulk-actions-toolbar"
            >
              <span class="selected-count">Выбрано: {{ selectedMetrics.length }}</span>
              <el-button
                size="small"
                @click="showBulkMoveDialog"
              >
                <el-icon><Folder /></el-icon>
                Перенести в категорию
              </el-button>
              <el-button
                size="small"
                type="danger"
                @click="handleBulkDelete"
              >
                <el-icon><Delete /></el-icon>
                Удалить выбранные
              </el-button>
              <el-button
                size="small"
                link
                @click="selectedMetrics = []"
              >
                Снять выбор
              </el-button>
            </div>

            <el-table
              v-if="filteredMetrics.length > 0"
              ref="metricsTableRef"
              :data="filteredMetrics"
              stripe
              style="width: 100%"
              max-height="600"
              @selection-change="handleSelectionChange"
            >
              <el-table-column
                type="selection"
                width="45"
              />
              <el-table-column
                label="Название"
                min-width="250"
              >
                <template #default="{ row }">
                  <div class="metric-name-cell">
                    <strong>{{ resolveMetricName(row) }}</strong>
                    <div
                      v-if="row.description"
                      class="metric-description"
                    >
                      {{ row.description }}
                    </div>
                  </div>
                </template>
              </el-table-column>

              <el-table-column
                prop="code"
                label="Код"
                width="180"
              >
                <template #default="{ row }">
                  <el-tag type="info">
                    {{ row.code }}
                  </el-tag>
                </template>
              </el-table-column>

              <el-table-column
                label="Статус"
                width="120"
                align="center"
              >
                <template #default="{ row }">
                  <el-switch
                    :model-value="row.active"
                    :loading="togglingIds.has(row.id)"
                    @change="(val) => handleToggleActive(row, val)"
                  />
                </template>
              </el-table-column>

              <el-table-column
                label="Действия"
                width="80"
                align="center"
              >
                <template #default="{ row }">
                  <el-dropdown
                    trigger="click"
                    @command="(cmd) => handleMetricCommand(cmd, row)"
                  >
                    <el-button
                      circle
                      size="small"
                    >
                      <el-icon><MoreFilled /></el-icon>
                    </el-button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="edit">
                          <el-icon><Edit /></el-icon>
                          Редактировать
                        </el-dropdown-item>
                        <el-dropdown-item
                          command="delete"
                          divided
                        >
                          <el-icon><Delete /></el-icon>
                          Удалить
                        </el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </template>
              </el-table-column>
            </el-table>

            <el-empty
              v-else
              description="Нет метрик"
            >
              <el-button
                type="primary"
                @click="showMetricDialog()"
              >
                <el-icon><Plus /></el-icon>
                Создать метрику
              </el-button>
            </el-empty>
          </div>
        </div>
      </div>
    </div>

    <!-- Диалог редактирования метрики -->
    <el-dialog
      v-model="metricDialogVisible"
      :title="editingMetric ? 'Редактировать метрику' : 'Создать метрику'"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="metricFormRef"
        :model="metricForm"
        :rules="metricRules"
        label-width="140px"
        label-position="top"
      >
        <el-form-item
          label="Код (уникальный идентификатор)"
          prop="code"
        >
          <el-input
            v-model="metricForm.code"
            :disabled="!!editingMetric"
            placeholder="communication_skills"
          />
        </el-form-item>

        <el-form-item
          label="Название (русское)"
          prop="name_ru"
        >
          <el-input
            v-model="metricForm.name_ru"
            placeholder="Коммуникативные навыки"
          />
        </el-form-item>

        <el-form-item
          label="Название (английское)"
          prop="name"
        >
          <el-input
            v-model="metricForm.name"
            placeholder="Communication Skills"
          />
        </el-form-item>

        <el-form-item label="Описание">
          <el-input
            v-model="metricForm.description"
            type="textarea"
            :rows="3"
            placeholder="Описание метрики..."
          />
        </el-form-item>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="Мин. значение">
              <el-input-number
                v-model="metricForm.min_value"
                :min="0"
                :max="10"
                :step="1"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Макс. значение">
              <el-input-number
                v-model="metricForm.max_value"
                :min="1"
                :max="10"
                :step="1"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="Категория">
          <el-select
            v-model="metricForm.category_id"
            placeholder="Выберите категорию"
            clearable
            style="width: 100%"
          >
            <el-option
              v-for="cat in categories"
              :key="cat.id"
              :label="cat.name"
              :value="cat.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="Статус">
          <el-switch
            v-model="metricForm.active"
            active-text="Активна"
            inactive-text="Неактивна"
          />
        </el-form-item>

        <!-- Секция синонимов (только при редактировании) -->
        <el-form-item
          v-if="editingMetric"
          label="Синонимы"
        >
          <div
            v-loading="synonymsLoading"
            class="synonyms-section"
          >
            <div class="synonyms-list">
              <template
                v-for="synonym in synonyms"
                :key="synonym.id"
              >
                <!-- Режим редактирования синонима -->
                <el-input
                  v-if="editingSynonymId === synonym.id"
                  v-model="editingSynonymText"
                  size="small"
                  class="synonym-edit-input"
                  @keyup.enter="saveEditingSynonym"
                  @keyup.escape="cancelEditingSynonym"
                  @blur="saveEditingSynonym"
                />
                <!-- Обычный tag -->
                <el-tag
                  v-else
                  closable
                  :disable-transitions="false"
                  @close="handleDeleteSynonym(synonym)"
                  @dblclick="startEditSynonym(synonym)"
                >
                  {{ synonym.synonym }}
                </el-tag>
              </template>
            </div>

            <div class="synonym-add-row">
              <el-input
                v-model="newSynonymText"
                placeholder="Новый синоним..."
                size="small"
                :disabled="synonymsSaving"
                @keyup.enter="handleAddSynonym"
              />
              <el-button
                type="primary"
                size="small"
                :loading="synonymsSaving"
                :disabled="!newSynonymText.trim()"
                @click="handleAddSynonym"
              >
                Добавить
              </el-button>
            </div>
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="metricDialogVisible = false">
          Отмена
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="saveMetric"
        >
          {{ editingMetric ? 'Сохранить' : 'Создать' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- Диалог редактирования категории -->
    <el-dialog
      v-model="categoryDialogVisible"
      :title="editingCategory ? 'Редактировать категорию' : 'Создать категорию'"
      width="500px"
    >
      <el-form
        :model="categoryForm"
        label-width="100px"
      >
        <el-form-item
          label="Название"
          required
        >
          <el-input
            v-model="categoryForm.name"
            placeholder="Soft Skills"
            @input="onCategoryNameInput"
          />
        </el-form-item>
        <el-form-item
          label="Код"
          required
        >
          <el-input
            v-model="categoryForm.code"
            placeholder="soft-skills"
            :disabled="!!editingCategory"
          >
            <template #append>
              <el-tooltip
                content="Код генерируется автоматически из названия. После создания изменить нельзя."
                placement="top"
              >
                <el-icon><InfoFilled /></el-icon>
              </el-tooltip>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="Описание">
          <el-input
            v-model="categoryForm.description"
            type="textarea"
            :rows="3"
            placeholder="Описание категории..."
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="categoryDialogVisible = false">
          Отмена
        </el-button>
        <el-button
          v-if="editingCategory"
          type="danger"
          @click="deleteCategory"
        >
          Удалить
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="saveCategory"
        >
          {{ editingCategory ? 'Сохранить' : 'Создать' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- Диалог подтверждения удаления -->
    <el-dialog
      v-model="deleteDialogVisible"
      title="Подтверждение удаления"
      width="500px"
    >
      <div v-if="metricToDelete">
        <p>Вы уверены, что хотите удалить метрику <strong>{{ resolveMetricName(metricToDelete) }}</strong>?</p>
        <el-alert
          v-if="metricUsage && (metricUsage.weight_tables_count > 0 || metricUsage.extracted_metrics_count > 0)"
          type="warning"
          :closable="false"
          show-icon
          style="margin-top: 16px"
        >
          <template #title>
            Эта метрика используется
          </template>
          <ul style="margin: 8px 0 0 0; padding-left: 20px">
            <li v-if="metricUsage.weight_tables_count > 0">
              В {{ metricUsage.weight_tables_count }} весовых таблицах
            </li>
            <li v-if="metricUsage.extracted_metrics_count > 0">
              В {{ metricUsage.extracted_metrics_count }} извлеченных метриках
            </li>
          </ul>
        </el-alert>
      </div>

      <template #footer>
        <el-button @click="deleteDialogVisible = false">
          Отмена
        </el-button>
        <el-button
          type="danger"
          :loading="deleting"
          @click="confirmDeleteMetric"
        >
          Удалить
        </el-button>
      </template>
    </el-dialog>

    <!-- Диалог bulk move -->
    <el-dialog
      v-model="bulkMoveDialogVisible"
      title="Перенести метрики в категорию"
      width="450px"
    >
      <p style="margin-bottom: 16px">
        Выберите категорию для {{ selectedMetrics.length }} метрик:
      </p>
      <el-select
        v-model="bulkTargetCategoryId"
        placeholder="Выберите категорию"
        clearable
        style="width: 100%"
      >
        <el-option
          label="Без категории"
          :value="null"
        />
        <el-option
          v-for="cat in categories"
          :key="cat.id"
          :label="cat.name"
          :value="cat.id"
        />
      </el-select>

      <template #footer>
        <el-button @click="bulkMoveDialogVisible = false">
          Отмена
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="confirmBulkMove"
        >
          Перенести
        </el-button>
      </template>
    </el-dialog>

    <!-- Диалог импорта -->
    <el-dialog
      v-model="importDialogVisible"
      title="Импорт метрик"
      width="600px"
    >
      <el-upload
        ref="uploadRef"
        drag
        :auto-upload="false"
        :limit="1"
        accept=".xlsx,.json"
        :on-change="handleFileChange"
      >
        <el-icon class="el-icon--upload">
          <Upload />
        </el-icon>
        <div class="el-upload__text">
          Перетащите файл сюда или <em>нажмите для выбора</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            Поддерживаются форматы: xlsx, json
          </div>
        </template>
      </el-upload>

      <template #footer>
        <el-button @click="importDialogVisible = false">
          Отмена
        </el-button>
        <el-button
          type="primary"
          :loading="importing"
          :disabled="!importFile"
          @click="confirmImport"
        >
          Импортировать
        </el-button>
      </template>
    </el-dialog>
  </app-layout>
</template>

<script setup>
import { ref, computed, onMounted, reactive, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus,
  Edit,
  Delete,
  Search,
  RefreshRight,
  Upload,
  Download,
  Folder,
  Menu,
  MoreFilled,
  InfoFilled,
  Rank
} from '@element-plus/icons-vue'
import draggable from 'vuedraggable'
import AppLayout from '@/components/AppLayout.vue'
import { metricsApi } from '@/api/metrics'
import { metricCategoriesApi } from '@/api/metricCategories'
import { metricSynonymsApi } from '@/api/metricSynonyms'
import { adminApi } from '@/api/admin'
import { getMetricDisplayName } from '@/utils/metricNames'

// Router for URL state
const route = useRoute()
const router = useRouter()

// State
const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const importing = ref(false)
const reindexing = ref(false)
const error = ref(null)
const searchQuery = ref('')

// Embedding stats
const embeddingStats = ref(null)

// Data
const allMetrics = ref([])
const categories = ref([])
const selectedCategoryId = ref(null)
const togglingIds = reactive(new Set())

// Dialogs
const metricDialogVisible = ref(false)
const categoryDialogVisible = ref(false)
const deleteDialogVisible = ref(false)
const importDialogVisible = ref(false)

// Editing state
const editingMetric = ref(null)
const editingCategory = ref(null)
const metricToDelete = ref(null)
const metricUsage = ref(null)
const importFile = ref(null)
const uploadRef = ref(null)

// Bulk selection
const selectedMetrics = ref([])
const bulkMoveDialogVisible = ref(false)
const bulkTargetCategoryId = ref(null)

// Synonyms state
const synonyms = ref([])
const synonymsLoading = ref(false)
const synonymsSaving = ref(false)
const newSynonymText = ref('')
const editingSynonymId = ref(null)
const editingSynonymText = ref('')

// Forms
const metricFormRef = ref(null)
const metricForm = ref({
  code: '',
  name: '',
  name_ru: '',
  description: '',
  min_value: 1,
  max_value: 10,
  active: true,
  category_id: null
})

const metricRules = {
  code: [
    { required: true, message: 'Введите код метрики', trigger: 'blur' },
    { min: 1, max: 50, message: 'От 1 до 50 символов', trigger: 'blur' }
  ],
  name_ru: [
    { required: true, message: 'Введите название', trigger: 'blur' }
  ]
}

const categoryForm = ref({
  code: '',
  name: '',
  description: ''
})

const generateSlug = (text) => {
  const cyrillic = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
  }
  return text.toLowerCase()
    .split('')
    .map(char => cyrillic[char] || char)
    .join('')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}

const warnedMetricCodes = new Set()

// Computed
const filteredMetrics = computed(() => {
  let metrics = allMetrics.value

  // Filter by category
  if (selectedCategoryId.value === 'uncategorized') {
    metrics = metrics.filter(m => !m.category_id)
  } else if (selectedCategoryId.value !== null) {
    metrics = metrics.filter(m => m.category_id === selectedCategoryId.value)
  }

  // Filter by search query
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    metrics = metrics.filter(m =>
      (m.name_ru && m.name_ru.toLowerCase().includes(query)) ||
      (m.name && m.name.toLowerCase().includes(query)) ||
      (m.code && m.code.toLowerCase().includes(query))
    )
  }

  return metrics
})

const selectedCategoryTitle = computed(() => {
  if (selectedCategoryId.value === null) {
    return 'Все метрики'
  }
  if (selectedCategoryId.value === 'uncategorized') {
    return 'Без категории'
  }
  if (!Array.isArray(categories.value)) {
    return 'Метрики'
  }
  const category = categories.value.find(c => c.id === selectedCategoryId.value)
  return category ? category.name : 'Метрики'
})

const uncategorizedMetricsCount = computed(() => {
  return allMetrics.value.filter(m => !m.category_id).length
})

// Methods
const resolveMetricName = (metric, fallbackCode) => {
  const code = metric?.code || fallbackCode
  const logger =
    code && warnedMetricCodes.has(code)
      ? { warn: () => {} }
      : {
          warn: (message) => {
            if (code) {
              warnedMetricCodes.add(code)
            }
            console.warn(message)
          }
        }
  return getMetricDisplayName(metric, code, logger)
}

const getMetricsCountByCategory = (categoryId) => {
  return allMetrics.value.filter(m => m.category_id === categoryId).length
}

const loadData = async () => {
  loading.value = true
  error.value = null
  try {
    const [metricsData, categoriesData] = await Promise.all([
      metricsApi.listMetricDefs(false),
      metricCategoriesApi.list().catch(() => ({ items: [] }))
    ])
    allMetrics.value = metricsData.items || []
    categories.value = categoriesData?.items || []

    // Load embedding stats in background
    loadEmbeddingStats()
  } catch (err) {
    console.error('Failed to load data:', err)
    error.value = 'Не удалось загрузить данные'
    ElMessage.error('Ошибка загрузки данных')
  } finally {
    loading.value = false
  }
}

const loadEmbeddingStats = async () => {
  try {
    embeddingStats.value = await adminApi.getEmbeddingStats()
  } catch (err) {
    // Silently fail - stats are optional
    console.warn('Failed to load embedding stats:', err)
    embeddingStats.value = null
  }
}

const handleReindexAll = async () => {
  try {
    await ElMessageBox.confirm(
      'Переиндексация обновит векторные представления всех метрик для семантического поиска. ' +
      'Это может занять несколько минут.',
      'Подтверждение переиндексации',
      {
        confirmButtonText: 'Переиндексировать',
        cancelButtonText: 'Отмена',
        type: 'info'
      }
    )

    reindexing.value = true
    const result = await adminApi.reindexAllMetrics()

    if (result.errors > 0) {
      ElMessage.warning(
        `Переиндексировано ${result.indexed} из ${result.total} метрик (${result.errors} ошибок)`
      )
    } else {
      ElMessage.success(`Переиндексировано ${result.indexed} метрик`)
    }

    // Refresh stats
    await loadEmbeddingStats()
  } catch (err) {
    if (err !== 'cancel') {
      console.error('Failed to reindex:', err)
      ElMessage.error(err.response?.data?.detail || 'Ошибка переиндексации')
    }
  } finally {
    reindexing.value = false
  }
}

const showMetricDialog = async (metric = null) => {
  editingMetric.value = metric
  // Reset synonyms state
  synonyms.value = []
  newSynonymText.value = ''
  editingSynonymId.value = null
  editingSynonymText.value = ''

  if (metric) {
    metricForm.value = {
      code: metric.code,
      name: metric.name || '',
      name_ru: metric.name_ru || '',
      description: metric.description || '',
      min_value: metric.min_value ?? 1,
      max_value: metric.max_value ?? 10,
      active: metric.active ?? true,
      category_id: metric.category_id || null
    }
    // Load synonyms for existing metric
    loadSynonyms(metric.id)
  } else {
    metricForm.value = {
      code: '',
      name: '',
      name_ru: '',
      description: '',
      min_value: 1,
      max_value: 10,
      active: true,
      category_id: selectedCategoryId.value === 'uncategorized' ? null : selectedCategoryId.value
    }
  }
  metricDialogVisible.value = true
}

const saveMetric = async () => {
  try {
    await metricFormRef.value?.validate()
  } catch {
    return
  }

  try {
    saving.value = true
    const data = { ...metricForm.value }

    if (editingMetric.value) {
      await metricsApi.updateMetricDef(editingMetric.value.id, data)
      ElMessage.success('Метрика обновлена')
    } else {
      await metricsApi.createMetricDef(data)
      ElMessage.success('Метрика создана')
    }

    metricDialogVisible.value = false
    await loadData()
  } catch (err) {
    console.error('Failed to save metric:', err)
    ElMessage.error(err.response?.data?.detail || 'Ошибка сохранения метрики')
  } finally {
    saving.value = false
  }
}

// Synonyms CRUD operations
const loadSynonyms = async (metricDefId) => {
  synonymsLoading.value = true
  try {
    const data = await metricSynonymsApi.getSynonyms(metricDefId)
    synonyms.value = data?.items || []
  } catch (err) {
    console.error('Failed to load synonyms:', err)
    synonyms.value = []
  } finally {
    synonymsLoading.value = false
  }
}

const handleAddSynonym = async () => {
  const text = newSynonymText.value.trim()
  // Guard: prevent double-click by checking synonymsSaving
  if (!text || !editingMetric.value || synonymsSaving.value) return

  synonymsSaving.value = true
  newSynonymText.value = ''  // Clear immediately to prevent visual double-click
  try {
    const created = await metricSynonymsApi.createSynonym(editingMetric.value.id, text)
    synonyms.value.push(created)
    ElMessage.success('Синоним добавлен')
  } catch (err) {
    console.error('Failed to add synonym:', err)
    if (err.response?.status === 409) {
      // Show enriched error if available
      const detail = err.response?.data?.detail
      if (detail?.existing_metric) {
        const metricName = detail.existing_metric.name_ru || detail.existing_metric.code
        ElMessage.error(`Синоним уже привязан к метрике «${metricName}»`)
      } else {
        ElMessage.error('Синоним уже существует')
      }
    } else {
      newSynonymText.value = text  // Restore on other errors
      ElMessage.error(err.response?.data?.detail || 'Ошибка добавления синонима')
    }
  } finally {
    synonymsSaving.value = false
  }
}

const handleDeleteSynonym = async (synonym) => {
  try {
    await metricSynonymsApi.deleteSynonym(synonym.id)
    synonyms.value = synonyms.value.filter(s => s.id !== synonym.id)
    ElMessage.success('Синоним удален')
  } catch (err) {
    console.error('Failed to delete synonym:', err)
    ElMessage.error(err.response?.data?.detail || 'Ошибка удаления синонима')
  }
}

const startEditSynonym = (synonym) => {
  editingSynonymId.value = synonym.id
  editingSynonymText.value = synonym.synonym
}

const cancelEditingSynonym = () => {
  editingSynonymId.value = null
  editingSynonymText.value = ''
}

const saveEditingSynonym = async () => {
  if (!editingSynonymId.value) return

  const text = editingSynonymText.value.trim()
  const originalSynonym = synonyms.value.find(s => s.id === editingSynonymId.value)

  // If empty or unchanged, cancel edit
  if (!text || text === originalSynonym?.synonym) {
    cancelEditingSynonym()
    return
  }

  try {
    const updated = await metricSynonymsApi.updateSynonym(editingSynonymId.value, text)
    const index = synonyms.value.findIndex(s => s.id === editingSynonymId.value)
    if (index !== -1) {
      synonyms.value[index] = updated
    }
    ElMessage.success('Синоним обновлен')
  } catch (err) {
    console.error('Failed to update synonym:', err)
    if (err.response?.status === 409) {
      ElMessage.error('Синоним уже существует')
    } else {
      ElMessage.error(err.response?.data?.detail || 'Ошибка обновления синонима')
    }
  } finally {
    cancelEditingSynonym()
  }
}

const handleToggleActive = async (metric, newValue) => {
  togglingIds.add(metric.id)
  try {
    await metricsApi.updateMetricDef(metric.id, { active: newValue })
    metric.active = newValue
    ElMessage.success(newValue ? 'Метрика активирована' : 'Метрика деактивирована')
  } catch (err) {
    console.error('Failed to toggle metric:', err)
    ElMessage.error('Ошибка изменения статуса')
  } finally {
    togglingIds.delete(metric.id)
  }
}

// Bulk operations
const metricsTableRef = ref(null)

const handleSelectionChange = (selection) => {
  selectedMetrics.value = selection
}

const showBulkMoveDialog = () => {
  bulkTargetCategoryId.value = null
  bulkMoveDialogVisible.value = true
}

const confirmBulkMove = async () => {
  if (selectedMetrics.value.length === 0) return

  try {
    // Fetch usage for selected metrics to show warning
    const usageChecks = await Promise.all(
      selectedMetrics.value.map(m => metricsApi.getUsage(m.id).catch(() => ({
        weight_tables_count: 0,
        extracted_metrics_count: 0
      })))
    )

    const totalWeightTables = usageChecks.reduce((sum, u) => sum + (u.weight_tables_count || 0), 0)
    const totalExtracted = usageChecks.reduce((sum, u) => sum + (u.extracted_metrics_count || 0), 0)
    const hasUsage = totalWeightTables > 0 || totalExtracted > 0

    if (hasUsage) {
      await ElMessageBox.confirm(
        `Выбранные метрики используются:\n` +
        `• В ${totalWeightTables} весовых таблицах\n` +
        `• В ${totalExtracted} извлечённых значениях\n\n` +
        `Продолжить перенос?`,
        'Подтверждение',
        { confirmButtonText: 'Перенести', cancelButtonText: 'Отмена', type: 'warning' }
      )
    }

    saving.value = true
    const metricIds = selectedMetrics.value.map(m => m.id)
    const result = await metricsApi.bulkMove(metricIds, bulkTargetCategoryId.value)

    if (result.success) {
      ElMessage.success(`${result.affected_count} метрик перенесено`)
      bulkMoveDialogVisible.value = false
      selectedMetrics.value = []
      await loadData()
    } else {
      const errorMessages = result.errors?.map(e => e.error).join(', ') || 'Неизвестная ошибка'
      ElMessage.error(`Ошибка: ${errorMessages}`)
    }
  } catch (err) {
    if (err !== 'cancel') {
      console.error('Failed to bulk move metrics:', err)
      ElMessage.error(err.response?.data?.detail || 'Ошибка переноса метрик')
    }
  } finally {
    saving.value = false
  }
}

const handleBulkDelete = async () => {
  if (selectedMetrics.value.length === 0) return

  try {
    // Fetch usage for all selected metrics
    const usageData = await Promise.all(
      selectedMetrics.value.map(m => metricsApi.getUsage(m.id).catch(() => ({
        extracted_metrics_count: 0,
        participant_metrics_count: 0,
        scoring_results_count: 0,
        weight_tables_count: 0
      })))
    )

    const totals = usageData.reduce((acc, u) => ({
      extracted: acc.extracted + (u.extracted_metrics_count || 0),
      participants: acc.participants + (u.participant_metrics_count || 0),
      scoring: acc.scoring + (u.scoring_results_count || 0),
      weightTables: acc.weightTables + (u.weight_tables_count || 0)
    }), { extracted: 0, participants: 0, scoring: 0, weightTables: 0 })

    const hasUsage = Object.values(totals).some(v => v > 0)

    // Build detailed message
    let message = `Будет удалено: ${selectedMetrics.value.length} метрик\n\n`

    if (hasUsage) {
      message += 'Также будут удалены:\n'
      if (totals.extracted > 0) {
        message += `• ${totals.extracted} извлечённых значений\n`
      }
      if (totals.participants > 0) {
        message += `• ${totals.participants} значений участников\n`
      }
      if (totals.scoring > 0) {
        message += `• ${totals.scoring} результатов скоринга\n`
      }
      if (totals.weightTables > 0) {
        message += `\nЗатронуты ${totals.weightTables} весовых таблиц (потребуется ручная корректировка)\n`
      }
      message += '\n'
    }

    message += 'Это действие необратимо.'

    await ElMessageBox.confirm(
      message,
      'Подтверждение удаления',
      {
        confirmButtonText: 'Удалить',
        cancelButtonText: 'Отмена',
        type: 'warning'
      }
    )

    saving.value = true
    const metricIds = selectedMetrics.value.map(m => m.id)
    const result = await metricsApi.bulkDelete(metricIds)

    if (result.success) {
      ElMessage.success(`${result.affected_count} метрик удалено`)
    } else {
      const errorCount = result.errors?.length || 0
      ElMessage.warning(`Удалено ${result.affected_count} метрик, ${errorCount} с ошибками`)
    }

    selectedMetrics.value = []
    await loadData()
  } catch (err) {
    if (err !== 'cancel') {
      console.error('Failed to bulk delete metrics:', err)
      ElMessage.error(err.response?.data?.detail || 'Ошибка удаления метрик')
    }
  } finally {
    saving.value = false
  }
}

const handleMetricCommand = async (command, metric) => {
  if (command === 'edit') {
    showMetricDialog(metric)
  } else if (command === 'delete') {
    metricToDelete.value = metric
    metricUsage.value = null
    deleteDialogVisible.value = true

    // Fetch usage in background
    try {
      metricUsage.value = await metricsApi.getUsage(metric.id)
    } catch {
      // Ignore errors fetching usage, allow deletion anyway
      metricUsage.value = { weight_tables_count: 0, extracted_metrics_count: 0 }
    }
  }
}

const confirmDeleteMetric = async () => {
  if (!metricToDelete.value) return

  try {
    deleting.value = true
    await metricsApi.deleteMetricDef(metricToDelete.value.id)
    ElMessage.success('Метрика удалена')
    deleteDialogVisible.value = false
    await loadData()
  } catch (err) {
    console.error('Failed to delete metric:', err)
    ElMessage.error(err.response?.data?.detail || 'Ошибка удаления метрики')
  } finally {
    deleting.value = false
    metricToDelete.value = null
    metricUsage.value = null
  }
}

const showCategoryDialog = (category = null) => {
  editingCategory.value = category
  if (category) {
    categoryForm.value = {
      code: category.code || '',
      name: category.name,
      description: category.description || ''
    }
  } else {
    categoryForm.value = {
      code: '',
      name: '',
      description: ''
    }
  }
  categoryDialogVisible.value = true
}

const onCategoryNameInput = () => {
  if (!editingCategory.value && categoryForm.value.name) {
    categoryForm.value.code = generateSlug(categoryForm.value.name)
  }
}

const onCategoriesReorder = async (evt) => {
  const { oldIndex, newIndex } = evt
  if (oldIndex === newIndex) return

  // Get the category that was moved (it's already at newIndex after vuedraggable moves it)
  const movedCategory = categories.value[newIndex]

  // Save state for rollback (copy before the move happened)
  const previousCategories = [...categories.value]
  // Undo the visual change to get original order
  previousCategories.splice(newIndex, 1)
  previousCategories.splice(oldIndex, 0, movedCategory)

  try {
    // UI is already updated by vuedraggable (optimistic)
    await metricCategoriesApi.reorder(movedCategory.id, newIndex)
    ElMessage.success('Порядок категорий обновлён')
  } catch (err) {
    // Rollback UI with animation
    categories.value = previousCategories
    console.error('Failed to reorder categories:', err)
    ElMessage.error('Ошибка сохранения порядка')
  }
}

const saveCategory = async () => {
  if (!categoryForm.value.name) {
    ElMessage.warning('Введите название категории')
    return
  }
  if (!editingCategory.value && !categoryForm.value.code) {
    ElMessage.warning('Введите код категории')
    return
  }

  try {
    saving.value = true
    if (editingCategory.value) {
      const { code: _code, ...updateData } = categoryForm.value
      await metricCategoriesApi.update(editingCategory.value.id, updateData)
      ElMessage.success('Категория обновлена')
    } else {
      await metricCategoriesApi.create(categoryForm.value)
      ElMessage.success('Категория создана')
    }

    categoryDialogVisible.value = false
    await loadData()
  } catch (err) {
    console.error('Failed to save category:', err)
    ElMessage.error(err.response?.data?.detail || 'Ошибка сохранения категории')
  } finally {
    saving.value = false
  }
}

const deleteCategory = async () => {
  if (!editingCategory.value?.id) {
    ElMessage.error('Категория не выбрана')
    return
  }

  const metricsCount = getMetricsCountByCategory(editingCategory.value.id)
  const warningMessage = metricsCount > 0
    ? `Удалить категорию "${editingCategory.value.name}" и ${metricsCount} метрик?\n\nЭто действие нельзя отменить.`
    : `Удалить категорию "${editingCategory.value.name}"?`

  try {
    await ElMessageBox.confirm(
      warningMessage,
      'Подтверждение удаления',
      {
        confirmButtonText: 'Удалить',
        cancelButtonText: 'Отмена',
        type: 'warning',
        dangerouslyUseHTMLString: false
      }
    )

    await metricCategoriesApi.delete(editingCategory.value.id)
    ElMessage.success('Категория удалена')
    categoryDialogVisible.value = false
    selectedCategoryId.value = null
    await loadData()
  } catch (err) {
    if (err !== 'cancel') {
      console.error('Failed to delete category:', err)
      ElMessage.error(err.response?.data?.detail || 'Ошибка удаления категории')
    }
  }
}

const handleExport = async () => {
  try {
    const blob = await metricsApi.exportMetrics('xlsx')
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `metrics_export_${new Date().toISOString().slice(0, 10)}.xlsx`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success('Экспорт завершен')
  } catch (err) {
    console.error('Failed to export metrics:', err)
    ElMessage.error('Ошибка экспорта')
  }
}

const handleImport = () => {
  importFile.value = null
  if (uploadRef.value) {
    uploadRef.value.clearFiles()
  }
  importDialogVisible.value = true
}

const handleFileChange = (file) => {
  importFile.value = file.raw
}

const confirmImport = async () => {
  if (!importFile.value) return

  try {
    importing.value = true
    const result = await metricsApi.importMetrics(importFile.value)
    ElMessage.success(`Импортировано: создано ${result.created_count || 0}, обновлено ${result.updated_count || 0}`)
    importDialogVisible.value = false
    await loadData()
  } catch (err) {
    console.error('Failed to import metrics:', err)
    ElMessage.error(err.response?.data?.detail || 'Ошибка импорта')
  } finally {
    importing.value = false
  }
}

// URL state synchronization
watch(selectedCategoryId, (newId) => {
  const query = newId === null ? {} :
                newId === 'uncategorized' ? { category: 'uncategorized' } :
                { category: newId }
  router.replace({ query })
})

// Init
onMounted(async () => {
  // Initialize from URL
  const categoryParam = route.query.category
  if (categoryParam === 'uncategorized') {
    selectedCategoryId.value = 'uncategorized'
  } else if (categoryParam) {
    selectedCategoryId.value = categoryParam
  }

  await loadData()
})
</script>

<style scoped>
.admin-competencies-view {
  max-width: 1600px;
  margin: 0 auto;
  padding: 20px;
}

/* Header */
.header-card {
  margin-bottom: 24px;
  border-radius: 12px;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-buttons {
  display: flex;
  gap: 12px;
}

.header-card h1 {
  margin: 0 0 8px 0;
  font-size: 28px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.header-card p {
  margin: 0;
  color: var(--color-text-regular);
  font-size: 15px;
}

/* Search */
.search-card {
  margin-bottom: 24px;
  border-radius: 12px;
}

/* Content */
.content-container {
  min-height: 400px;
}

.main-layout {
  display: flex;
  gap: 24px;
}

/* Sidebar */
.categories-sidebar {
  width: 280px;
  flex-shrink: 0;
  background-color: var(--color-bg-overlay);
  border-radius: 12px;
  padding: 16px;
  border: 1px solid var(--color-border-light);
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.sidebar-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.category-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.category-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.category-item:hover {
  background-color: var(--color-bg-hover);
}

.category-item.active {
  background-color: var(--color-primary-bg);
  color: var(--color-primary);
}

.category-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.category-item .edit-btn {
  opacity: 0;
  transition: opacity 0.2s;
}

.category-item:hover .edit-btn {
  opacity: 1;
}

.category-item .drag-handle {
  cursor: grab;
  color: var(--color-text-placeholder);
  transition: color 0.2s;
}

.category-item:hover .drag-handle {
  color: var(--color-text-regular);
}

.category-ghost {
  opacity: 0.5;
  background-color: var(--color-primary-bg);
}

.category-drag-over {
  background-color: var(--el-color-primary-light-9);
  border: 2px dashed var(--el-color-primary);
  border-radius: 8px;
}

.sortable-chosen {
  background-color: var(--color-primary-bg);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

/* Metrics content */
.metrics-content {
  flex: 1;
  background-color: var(--color-bg-overlay);
  border-radius: 12px;
  padding: 20px;
  border: 1px solid var(--color-border-light);
}

.metrics-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.metrics-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

/* Bulk actions */
.bulk-actions-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background-color: var(--color-primary-bg);
  border-radius: 8px;
  margin-bottom: 16px;
}

.bulk-actions-toolbar .selected-count {
  font-weight: 500;
  color: var(--color-primary);
}

/* Metric table cells */
.metric-name-cell {
  padding: 8px 0;
}

.metric-description {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.4;
}

/* Synonyms section */
.synonyms-section {
  width: 100%;
  min-height: 60px;
}

.synonyms-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  min-height: 32px;
}

.synonyms-list .el-tag {
  cursor: default;
}

.synonyms-list .el-tag:hover {
  background-color: var(--el-tag-hover-bg-color, var(--el-color-primary-light-9));
}

.synonym-edit-input {
  width: 150px;
}

.synonym-add-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.synonym-add-row .el-input {
  flex: 1;
}

/* Responsive */
@media (max-width: 900px) {
  .main-layout {
    flex-direction: column;
  }

  .categories-sidebar {
    width: 100%;
  }
}
</style>
