<template>
  <app-layout>
    <div
      v-loading="loading"
      class="org-detail"
    >
      <!-- Organization Info Card -->
      <el-card
        v-if="organization"
        class="detail-card"
      >
        <template #header>
          <div class="card-header">
            <h2>{{ organization.name }}</h2>
            <div class="header-actions">
              <el-button @click="router.push('/organizations')">
                Назад
              </el-button>
              <el-button
                type="primary"
                @click="showEditDialog = true"
              >
                Редактировать
              </el-button>
            </div>
          </div>
        </template>

        <el-descriptions
          :column="isMobile ? 1 : 2"
          border
        >
          <el-descriptions-item label="Название">
            {{ organization.name }}
          </el-descriptions-item>
          <el-descriptions-item label="Описание">
            {{ organization.description || 'Не указано' }}
          </el-descriptions-item>
          <el-descriptions-item label="Дата создания">
            {{ formatDate(organization.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="Кол-во отделов">
            {{ organization.departments?.length || 0 }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- Departments Section -->
      <div
        v-if="organization"
        class="departments-section"
      >
        <div class="section-header">
          <h3>Отделы</h3>
          <el-button
            type="primary"
            @click="showDeptDialog = true"
          >
            <el-icon><Plus /></el-icon>
            Добавить отдел
          </el-button>
        </div>

        <el-empty
          v-if="!organization.departments?.length"
          description="Нет отделов"
          :image-size="80"
        />

        <div
          v-else
          class="departments-list"
        >
          <div
            v-for="dept in organization.departments"
            :key="dept.id"
            class="dept-item"
          >
            <div class="dept-header">
              <div
                class="dept-title"
                @click="toggleDeptExpand(dept.id)"
              >
                <el-icon class="dept-expand-icon" :class="{ 'is-expanded': expandedDepts[dept.id] }">
                  <ArrowRight />
                </el-icon>
                <span class="dept-name">{{ dept.name }}</span>
                <el-tag size="small" type="info">
                  {{ dept.participants_count }} уч.
                </el-tag>
                <el-tag
                  v-if="dept.weight_table_name"
                  size="small"
                  type="success"
                >
                  {{ dept.weight_table_name }}
                </el-tag>
                <el-tag
                  v-else
                  size="small"
                  type="info"
                  effect="plain"
                >
                  Нет весовой таблицы
                </el-tag>
              </div>
              <div class="dept-actions">
                <el-button
                  size="small"
                  plain
                  @click="openWeightTableDialog(dept)"
                >
                  Весовая таблица
                </el-button>
                <el-button
                  size="small"
                  type="primary"
                  plain
                  @click="openAddParticipantDialog(dept)"
                >
                  <el-icon><Plus /></el-icon>
                  Добавить
                </el-button>
                <el-button
                  size="small"
                  @click="openEditDeptDialog(dept)"
                >
                  Изменить
                </el-button>
                <el-button
                  size="small"
                  type="danger"
                  plain
                  @click="confirmDeleteDept(dept)"
                >
                  Удалить
                </el-button>
              </div>
            </div>

            <div v-if="dept.description && expandedDepts[dept.id]" class="dept-description">
              {{ dept.description }}
            </div>

            <!-- Expanded participants list -->
            <div
              v-if="expandedDepts[dept.id]"
              v-loading="loadingParticipants[dept.id]"
              class="dept-participants"
            >
              <!-- Calculate scores button -->
              <div v-if="dept.weight_table_id" class="scores-toolbar">
                <el-button
                  type="primary"
                  size="small"
                  :loading="calculatingScores[dept.id]"
                  @click="handleCalculateScores(dept)"
                >
                  Рассчитать соответствие
                </el-button>
              </div>

              <el-empty
                v-if="!deptParticipants[dept.id]?.length"
                description="Нет участников"
                :image-size="60"
              />

              <el-table
                v-else
                :data="deptParticipants[dept.id]"
                size="small"
                stripe
                :default-sort="dept.weight_table_id ? { prop: 'suitability_pct', order: 'descending' } : {}"
              >
                <el-table-column
                  label="ФИО"
                >
                  <template #default="{ row }">
                    <el-link
                      type="primary"
                      :underline="false"
                      @click="router.push(`/participants/${row.id}`)"
                    >
                      {{ row.full_name }}
                    </el-link>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="external_id"
                  label="Внешний ID"
                  width="150"
                />
                <el-table-column
                  v-if="dept.weight_table_id"
                  label="Соответствие"
                  prop="suitability_pct"
                  width="180"
                  sortable
                >
                  <template #default="{ row }">
                    <template v-if="!row.has_metrics">
                      <el-tag size="small" type="info">Нет данных</el-tag>
                    </template>
                    <template v-else-if="row.suitability_pct == null">
                      <el-tag size="small" type="warning">Не рассчитано</el-tag>
                    </template>
                    <template v-else>
                      <el-progress
                        :percentage="row.suitability_pct"
                        :color="getSuitabilityColor(row.suitability_pct)"
                        :stroke-width="14"
                        :text-inside="true"
                        :format="(pct) => pct.toFixed(1) + '%'"
                      />
                    </template>
                  </template>
                </el-table-column>
                <el-table-column
                  v-if="dept.weight_table_id"
                  label="Покрытие"
                  prop="metrics_coverage"
                  width="120"
                  sortable
                >
                  <template #default="{ row }">
                    <span v-if="row.metrics_coverage != null">{{ row.metrics_coverage }}%</span>
                    <span v-else class="text-muted">-</span>
                  </template>
                </el-table-column>
                <el-table-column
                  label=""
                  width="240"
                  align="center"
                >
                  <template #default="{ row }">
                    <el-button
                      type="primary"
                      size="small"
                      plain
                      @click="router.push(`/participants/${row.id}`)"
                    >
                      Профиль
                    </el-button>
                    <el-button
                      type="warning"
                      size="small"
                      plain
                      @click="confirmDetach(dept, row)"
                    >
                      Отвязать
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </div>
      </div>

      <!-- Edit Organization Dialog -->
      <el-dialog
        v-model="showEditDialog"
        title="Редактировать организацию"
        :width="isMobile ? '95%' : '500px'"
      >
        <el-form
          ref="editFormRef"
          :model="editForm"
          :rules="editRules"
          label-position="top"
        >
          <el-form-item
            label="Название"
            prop="name"
          >
            <el-input v-model="editForm.name" />
          </el-form-item>
          <el-form-item
            label="Описание"
            prop="description"
          >
            <el-input
              v-model="editForm.description"
              type="textarea"
              :rows="3"
            />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showEditDialog = false">
            Отмена
          </el-button>
          <el-button
            type="primary"
            :loading="saving"
            @click="handleEditOrg"
          >
            Сохранить
          </el-button>
        </template>
      </el-dialog>

      <!-- Create Department Dialog -->
      <el-dialog
        v-model="showDeptDialog"
        title="Добавить отдел"
        :width="isMobile ? '95%' : '500px'"
      >
        <el-form
          ref="deptFormRef"
          :model="deptForm"
          :rules="deptRules"
          label-position="top"
        >
          <el-form-item
            label="Название"
            prop="name"
          >
            <el-input
              v-model="deptForm.name"
              placeholder="Введите название отдела"
            />
          </el-form-item>
          <el-form-item
            label="Описание"
            prop="description"
          >
            <el-input
              v-model="deptForm.description"
              type="textarea"
              :rows="3"
              placeholder="Описание (необязательно)"
            />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showDeptDialog = false">
            Отмена
          </el-button>
          <el-button
            type="primary"
            :loading="saving"
            @click="handleCreateDept"
          >
            Создать
          </el-button>
        </template>
      </el-dialog>

      <!-- Edit Department Dialog -->
      <el-dialog
        v-model="showEditDeptDialog"
        title="Редактировать отдел"
        :width="isMobile ? '95%' : '500px'"
      >
        <el-form
          ref="editDeptFormRef"
          :model="editDeptForm"
          :rules="deptRules"
          label-position="top"
        >
          <el-form-item
            label="Название"
            prop="name"
          >
            <el-input v-model="editDeptForm.name" />
          </el-form-item>
          <el-form-item
            label="Описание"
            prop="description"
          >
            <el-input
              v-model="editDeptForm.description"
              type="textarea"
              :rows="3"
            />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showEditDeptDialog = false">
            Отмена
          </el-button>
          <el-button
            type="primary"
            :loading="saving"
            @click="handleEditDept"
          >
            Сохранить
          </el-button>
        </template>
      </el-dialog>

      <!-- Weight Table Selection Dialog -->
      <el-dialog
        v-model="showWeightTableDialog"
        title="Весовая таблица"
        :width="isMobile ? '95%' : '500px'"
      >
        <p style="margin-bottom: 16px; color: var(--color-text-secondary)">
          Выберите весовую таблицу для отдела "{{ weightTableDept?.name }}"
        </p>
        <el-select
          v-model="selectedWeightTableId"
          placeholder="Выберите весовую таблицу"
          filterable
          clearable
          style="width: 100%"
          :loading="loadingWeightTables"
        >
          <el-option
            v-for="wt in weightTableOptions"
            :key="wt.id"
            :label="wt.prof_activity_name"
            :value="wt.id"
          />
        </el-select>
        <template #footer>
          <el-button
            v-if="weightTableDept?.weight_table_id"
            type="danger"
            plain
            :loading="saving"
            @click="handleDetachWeightTable"
          >
            Отвязать
          </el-button>
          <el-button @click="showWeightTableDialog = false">
            Отмена
          </el-button>
          <el-button
            type="primary"
            :loading="saving"
            :disabled="!selectedWeightTableId"
            @click="handleAttachWeightTable"
          >
            Сохранить
          </el-button>
        </template>
      </el-dialog>

      <!-- Add Participant to Department Drawer -->
      <el-drawer
        v-model="showAddParticipantDrawer"
        :title="'Добавить участника — ' + (currentDeptForAttach?.name || '')"
        :size="isMobile ? '100%' : '480px'"
        direction="rtl"
        destroy-on-close
      >
        <el-tabs v-model="addParticipantTab">
          <el-tab-pane
            label="Найти существующего"
            name="existing"
          >
            <el-input
              v-model="participantSearchQuery"
              placeholder="Поиск по имени..."
              clearable
              :prefix-icon="Search"
              style="margin-bottom: var(--spacing-md)"
              @input="onParticipantSearchInput"
            />
            <div
              v-loading="searchingParticipants"
              class="participant-search-list"
            >
              <el-empty
                v-if="!searchingParticipants && !participantOptions.length"
                description="Участники не найдены"
                :image-size="60"
              />
              <el-checkbox-group
                v-else
                v-model="selectedParticipantIds"
              >
                <div
                  v-for="p in participantOptions"
                  :key="p.id"
                  class="participant-search-item"
                >
                  <el-checkbox :value="p.id">
                    <span>{{ p.full_name }}</span>
                    <span
                      v-if="p.external_id"
                      class="participant-ext-id"
                    >
                      {{ p.external_id }}
                    </span>
                  </el-checkbox>
                </div>
              </el-checkbox-group>
            </div>
            <el-button
              type="primary"
              :loading="saving"
              :disabled="!selectedParticipantIds.length"
              style="width: 100%; margin-top: var(--spacing-md)"
              @click="handleAttachParticipants"
            >
              Привязать ({{ selectedParticipantIds.length }})
            </el-button>
          </el-tab-pane>

          <el-tab-pane
            label="Создать нового"
            name="create"
          >
            <el-form
              ref="newParticipantFormRef"
              :model="newParticipantForm"
              :rules="newParticipantRules"
              label-position="top"
            >
              <el-form-item
                label="ФИО"
                prop="full_name"
              >
                <el-input
                  v-model="newParticipantForm.full_name"
                  placeholder="Введите полное имя"
                />
              </el-form-item>
              <el-form-item
                label="Дата рождения"
                prop="birth_date"
              >
                <el-date-picker
                  v-model="newParticipantForm.birth_date"
                  type="date"
                  placeholder="Выберите дату"
                  format="YYYY-MM-DD"
                  value-format="YYYY-MM-DD"
                  style="width: 100%"
                />
              </el-form-item>
              <el-form-item
                label="Внешний ID"
                prop="external_id"
              >
                <el-input
                  v-model="newParticipantForm.external_id"
                  placeholder="Внешний идентификатор (необязательно)"
                />
              </el-form-item>
            </el-form>
            <el-button
              type="primary"
              :loading="saving"
              style="width: 100%; margin-top: var(--spacing-md)"
              @click="handleCreateAndAttach"
            >
              Создать и привязать
            </el-button>
          </el-tab-pane>
        </el-tabs>
      </el-drawer>
    </div>
  </app-layout>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, ArrowRight } from '@element-plus/icons-vue'
import AppLayout from '@/components/AppLayout.vue'
import { organizationsApi, weightsApi } from '@/api'
import { participantsApi } from '@/api'
import { formatDate } from '@/utils/dateFormat'
import { useResponsive } from '@/composables/useResponsive'

const router = useRouter()
const route = useRoute()
const { isMobile } = useResponsive()

const loading = ref(false)
const saving = ref(false)
const organization = ref(null)

// Department expansion
const expandedDepts = ref({})
const deptParticipants = ref({})
const loadingParticipants = ref({})
const calculatingScores = ref({})

// Edit org
const showEditDialog = ref(false)
const editFormRef = ref(null)
const editForm = reactive({ name: '', description: '' })
const editRules = {
  name: [
    { required: true, message: 'Введите название', trigger: 'blur' }
  ]
}

// Create dept
const showDeptDialog = ref(false)
const deptFormRef = ref(null)
const deptForm = reactive({ name: '', description: '' })
const deptRules = {
  name: [
    { required: true, message: 'Введите название отдела', trigger: 'blur' }
  ]
}

// Edit dept
const showEditDeptDialog = ref(false)
const editDeptFormRef = ref(null)
const editDeptForm = reactive({ id: null, name: '', description: '' })

// Weight table dialog
const showWeightTableDialog = ref(false)
const weightTableDept = ref(null)
const selectedWeightTableId = ref(null)
const weightTableOptions = ref([])
const loadingWeightTables = ref(false)

// Add participant drawer
const showAddParticipantDrawer = ref(false)
const addParticipantTab = ref('existing')
const currentDeptForAttach = ref(null)
const selectedParticipantIds = ref([])
const participantOptions = ref([])
const searchingParticipants = ref(false)
const participantSearchQuery = ref('')
let searchDebounceTimer = null

// Create new participant inside drawer
const newParticipantFormRef = ref(null)
const newParticipantForm = reactive({ full_name: '', birth_date: '', external_id: '' })
const newParticipantRules = {
  full_name: [
    { required: true, message: 'Введите ФИО', trigger: 'blur' },
    { min: 1, max: 255, message: 'От 1 до 255 символов', trigger: 'blur' }
  ]
}

const getSuitabilityColor = (pct) => {
  if (pct >= 80) return '#67C23A'
  if (pct >= 60) return '#E6A23C'
  if (pct >= 40) return '#F56C6C'
  return '#909399'
}

const loadOrganization = async () => {
  loading.value = true
  try {
    const data = await organizationsApi.getById(route.params.id)
    organization.value = data
  } catch (error) {
    ElMessage.error('Организация не найдена')
    router.push('/organizations')
  } finally {
    loading.value = false
  }
}

// --- Org edit ---

const handleEditOrg = async () => {
  if (!editFormRef.value) return
  await editFormRef.value.validate(async (valid) => {
    if (!valid) return
    saving.value = true
    try {
      await organizationsApi.update(route.params.id, editForm)
      ElMessage.success('Организация обновлена')
      showEditDialog.value = false
      await loadOrganization()
    } catch (error) {
      ElMessage.error(error.response?.data?.detail || 'Ошибка обновления')
    } finally {
      saving.value = false
    }
  })
}

// --- Department CRUD ---

const handleCreateDept = async () => {
  if (!deptFormRef.value) return
  await deptFormRef.value.validate(async (valid) => {
    if (!valid) return
    saving.value = true
    try {
      await organizationsApi.createDepartment(route.params.id, deptForm)
      ElMessage.success('Отдел создан')
      showDeptDialog.value = false
      deptForm.name = ''
      deptForm.description = ''
      await loadOrganization()
    } catch (error) {
      ElMessage.error(error.response?.data?.detail || 'Ошибка создания отдела')
    } finally {
      saving.value = false
    }
  })
}

const openEditDeptDialog = (dept) => {
  editDeptForm.id = dept.id
  editDeptForm.name = dept.name
  editDeptForm.description = dept.description || ''
  showEditDeptDialog.value = true
}

const handleEditDept = async () => {
  if (!editDeptFormRef.value) return
  await editDeptFormRef.value.validate(async (valid) => {
    if (!valid) return
    saving.value = true
    try {
      await organizationsApi.updateDepartment(route.params.id, editDeptForm.id, {
        name: editDeptForm.name,
        description: editDeptForm.description
      })
      ElMessage.success('Отдел обновлён')
      showEditDeptDialog.value = false
      await loadOrganization()
    } catch (error) {
      ElMessage.error(error.response?.data?.detail || 'Ошибка обновления отдела')
    } finally {
      saving.value = false
    }
  })
}

const confirmDeleteDept = (dept) => {
  ElMessageBox.confirm(
    `Удалить отдел "${dept.name}"? Участники будут отвязаны, но не удалены.`,
    'Подтверждение',
    { confirmButtonText: 'Удалить', cancelButtonText: 'Отмена', type: 'warning' }
  ).then(async () => {
    try {
      await organizationsApi.deleteDepartment(route.params.id, dept.id)
      ElMessage.success('Отдел удалён')
      await loadOrganization()
    } catch (error) {
      ElMessage.error('Ошибка удаления отдела')
    }
  }).catch(() => {})
}

// --- Weight table ---

const openWeightTableDialog = async (dept) => {
  weightTableDept.value = dept
  selectedWeightTableId.value = dept.weight_table_id || null
  showWeightTableDialog.value = true
  loadingWeightTables.value = true
  try {
    const data = await weightsApi.list()
    weightTableOptions.value = (data.items || data).map(wt => ({
      id: wt.id,
      prof_activity_name: wt.prof_activity_name || wt.prof_activity?.name || 'Без названия'
    }))
  } catch {
    weightTableOptions.value = []
    ElMessage.error('Ошибка загрузки весовых таблиц')
  } finally {
    loadingWeightTables.value = false
  }
}

const handleAttachWeightTable = async () => {
  if (!selectedWeightTableId.value || !weightTableDept.value) return
  saving.value = true
  try {
    await organizationsApi.attachWeightTable(
      route.params.id,
      weightTableDept.value.id,
      selectedWeightTableId.value
    )
    ElMessage.success('Весовая таблица привязана')
    showWeightTableDialog.value = false
    await loadOrganization()
    if (expandedDepts.value[weightTableDept.value.id]) {
      await loadDeptParticipants(weightTableDept.value.id)
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || 'Ошибка привязки весовой таблицы')
  } finally {
    saving.value = false
  }
}

const handleDetachWeightTable = async () => {
  if (!weightTableDept.value) return
  saving.value = true
  try {
    await organizationsApi.attachWeightTable(
      route.params.id,
      weightTableDept.value.id,
      null
    )
    ElMessage.success('Весовая таблица отвязана')
    showWeightTableDialog.value = false
    await loadOrganization()
    if (expandedDepts.value[weightTableDept.value.id]) {
      await loadDeptParticipants(weightTableDept.value.id)
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || 'Ошибка отвязки весовой таблицы')
  } finally {
    saving.value = false
  }
}

const handleCalculateScores = async (dept) => {
  calculatingScores.value[dept.id] = true
  try {
    const result = await organizationsApi.calculateDepartmentScores(route.params.id, dept.id)
    ElMessage.success(`Рассчитано: ${result.calculated}` + (result.errors?.length ? `, ошибок: ${result.errors.length}` : ''))
    await loadDeptParticipants(dept.id)
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || 'Ошибка расчёта')
  } finally {
    calculatingScores.value[dept.id] = false
  }
}

// --- Participants ---

const toggleDeptExpand = async (deptId) => {
  if (expandedDepts.value[deptId]) {
    expandedDepts.value[deptId] = false
    return
  }
  expandedDepts.value[deptId] = true
  await loadDeptParticipants(deptId)
}

const loadDeptParticipants = async (deptId) => {
  loadingParticipants.value[deptId] = true
  try {
    const dept = organization.value?.departments?.find(d => d.id === deptId)
    let data
    if (dept?.weight_table_id) {
      data = await organizationsApi.listDepartmentParticipantsWithScores(route.params.id, deptId)
    } else {
      data = await organizationsApi.listDepartmentParticipants(route.params.id, deptId)
    }
    deptParticipants.value[deptId] = data
  } catch (error) {
    ElMessage.error('Ошибка загрузки участников отдела')
  } finally {
    loadingParticipants.value[deptId] = false
  }
}

const openAddParticipantDialog = async (dept) => {
  currentDeptForAttach.value = dept
  selectedParticipantIds.value = []
  participantOptions.value = []
  participantSearchQuery.value = ''
  addParticipantTab.value = 'existing'
  newParticipantForm.full_name = ''
  newParticipantForm.birth_date = ''
  newParticipantForm.external_id = ''
  showAddParticipantDrawer.value = true
  // Preload participants so the user sees them immediately
  await searchParticipants('')
}

const searchParticipants = async (query) => {
  searchingParticipants.value = true
  try {
    const params = { size: 50 }
    if (query && query.length >= 2) {
      params.query = query
    }
    const data = await participantsApi.search(params)
    participantOptions.value = data.items || []
  } catch {
    participantOptions.value = []
  } finally {
    searchingParticipants.value = false
  }
}

const onParticipantSearchInput = (val) => {
  clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    searchParticipants(val)
  }, 300)
}

const handleAttachParticipants = async () => {
  if (!selectedParticipantIds.value.length || !currentDeptForAttach.value) return
  saving.value = true
  try {
    await organizationsApi.attachParticipants(
      route.params.id,
      currentDeptForAttach.value.id,
      selectedParticipantIds.value
    )
    ElMessage.success('Участники привязаны')
    showAddParticipantDrawer.value = false
    await loadOrganization()
    // Refresh expanded dept if it was expanded
    if (expandedDepts.value[currentDeptForAttach.value.id]) {
      await loadDeptParticipants(currentDeptForAttach.value.id)
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || 'Ошибка привязки участников')
  } finally {
    saving.value = false
  }
}

const handleCreateAndAttach = async () => {
  if (!newParticipantFormRef.value || !currentDeptForAttach.value) return
  await newParticipantFormRef.value.validate(async (valid) => {
    if (!valid) return
    saving.value = true
    try {
      // Create participant
      const created = await participantsApi.create({
        full_name: newParticipantForm.full_name,
        birth_date: newParticipantForm.birth_date || null,
        external_id: newParticipantForm.external_id || null,
      })
      // Attach to department
      await organizationsApi.attachParticipants(
        route.params.id,
        currentDeptForAttach.value.id,
        [created.id]
      )
      ElMessage.success(`Участник "${created.full_name}" создан и привязан`)
      showAddParticipantDrawer.value = false
      await loadOrganization()
      if (expandedDepts.value[currentDeptForAttach.value.id]) {
        await loadDeptParticipants(currentDeptForAttach.value.id)
      }
    } catch (error) {
      ElMessage.error(error.response?.data?.detail || 'Ошибка создания участника')
    } finally {
      saving.value = false
    }
  })
}

const confirmDetach = (dept, participant) => {
  ElMessageBox.confirm(
    `Отвязать "${participant.full_name}" от отдела "${dept.name}"?`,
    'Подтверждение',
    { confirmButtonText: 'Отвязать', cancelButtonText: 'Отмена', type: 'warning' }
  ).then(async () => {
    try {
      await organizationsApi.detachParticipant(route.params.id, dept.id, participant.id)
      ElMessage.success('Участник отвязан')
      await loadOrganization()
      await loadDeptParticipants(dept.id)
    } catch (error) {
      ElMessage.error('Ошибка отвязки участника')
    }
  }).catch(() => {})
}

onMounted(async () => {
  await loadOrganization()
  // Populate edit form
  if (organization.value) {
    editForm.name = organization.value.name
    editForm.description = organization.value.description || ''
  }
})
</script>

<style scoped>
.org-detail {
  max-width: var(--container-max-width);
  margin: 0 auto;
}

.detail-card {
  margin-bottom: var(--spacing-xl);
  background-color: var(--color-bg-card);
  border: 1px solid var(--card-border-color);
  border-radius: var(--card-border-radius);
  box-shadow: var(--card-shadow);
  transition: var(--transition-base);
}

.detail-card:hover {
  box-shadow: var(--shadow-card-hover);
}

.detail-card :deep(.el-card__header) {
  padding: var(--spacing-lg) var(--spacing-xl);
  border-bottom: 1px solid var(--color-border-light);
  background-color: transparent;
}

.detail-card :deep(.el-card__body) {
  padding: var(--spacing-xl);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--spacing-lg);
}

.card-header h2 {
  margin: 0;
  font-size: var(--font-size-h1);
  color: var(--color-text-primary);
  font-weight: var(--font-weight-semibold);
}

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
}

.section-header h3 {
  margin: 0;
  font-size: var(--font-size-h2);
  color: var(--color-text-primary);
  font-weight: var(--font-weight-semibold);
}

:deep(.el-descriptions) {
  --el-descriptions-item-bordered-label-background: var(--color-gray-50);
}

:deep(.el-descriptions__label) {
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
}

:deep(.el-descriptions__content) {
  color: var(--color-text-primary);
}

:deep(.el-descriptions__body) {
  border-radius: var(--border-radius-base);
  overflow: hidden;
}

/* Departments Section */
.departments-section {
  margin-bottom: var(--spacing-xl);
}

.departments-list {
  background-color: var(--color-bg-card);
  border: 1px solid var(--card-border-color);
  border-radius: var(--card-border-radius);
  overflow: hidden;
}

.dept-item {
  border-bottom: 1px solid var(--color-border-light);
}

.dept-item:last-child {
  border-bottom: none;
}

.dept-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-md) var(--spacing-lg);
  flex-wrap: wrap;
  gap: var(--spacing-md);
}

.dept-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  cursor: pointer;
  user-select: none;
  flex-wrap: wrap;
}

.dept-title:hover .dept-name {
  color: var(--el-color-primary);
}

.dept-expand-icon {
  transition: transform 0.2s;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.dept-expand-icon.is-expanded {
  transform: rotate(90deg);
}

.dept-name {
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  transition: color 0.15s;
}

.dept-actions {
  display: flex;
  gap: var(--spacing-xs);
  flex-wrap: wrap;
}

.dept-description {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  padding: 0 var(--spacing-lg) var(--spacing-md) calc(var(--spacing-lg) + 20px);
}

.dept-participants {
  padding: var(--spacing-md) var(--spacing-lg) var(--spacing-lg);
}

.scores-toolbar {
  margin-bottom: var(--spacing-md);
  display: flex;
  gap: var(--spacing-sm);
}

.text-muted {
  color: var(--color-text-secondary);
}

/* Participant search list in drawer */
.participant-search-list {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid var(--color-border-light);
  border-radius: var(--border-radius-base);
  padding: var(--spacing-sm);
  min-height: 100px;
}

.participant-search-item {
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--border-radius-base);
  transition: background-color 0.15s;
}

.participant-search-item:hover {
  background-color: var(--color-bg-section);
}

.participant-search-item :deep(.el-checkbox__label) {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.participant-ext-id {
  color: var(--color-text-secondary);
  font-size: 12px;
}

/* Dialogs */
:deep(.el-dialog) {
  border-radius: var(--border-radius-xl);
  box-shadow: var(--shadow-xl);
}

:deep(.el-dialog__header) {
  padding: var(--spacing-xl) var(--spacing-xl) var(--spacing-lg);
  border-bottom: 1px solid var(--color-border-light);
}

:deep(.el-dialog__title) {
  color: var(--color-text-primary);
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-lg);
}

:deep(.el-dialog__body) {
  padding: var(--spacing-xl);
}

:deep(.el-dialog__footer) {
  padding: var(--spacing-lg) var(--spacing-xl);
  border-top: 1px solid var(--color-border-light);
}

@media (max-width: 768px) {
  .detail-card :deep(.el-card__header),
  .detail-card :deep(.el-card__body) {
    padding: var(--spacing-lg);
  }

  .card-header {
    flex-direction: column;
    align-items: stretch;
  }

  .card-header h2 {
    font-size: var(--font-size-h2);
  }

  .header-actions {
    flex-direction: column;
  }

  .header-actions .el-button {
    min-height: var(--button-height-large);
    width: 100%;
  }

  .section-header {
    flex-direction: column;
    align-items: stretch;
    gap: var(--spacing-md);
  }

  .section-header .el-button {
    width: 100%;
    min-height: var(--button-height-large);
  }

  .dept-header {
    flex-direction: column;
    align-items: stretch;
  }

  .dept-actions {
    flex-direction: column;
  }

  .dept-actions .el-button {
    width: 100%;
  }
}
</style>
