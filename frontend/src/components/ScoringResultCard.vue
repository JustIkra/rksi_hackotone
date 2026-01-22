<template>
  <el-card class="scoring-card">
    <h4>{{ result.prof_activity_name }}</h4>
    <div class="scoring-result">
      <div class="score-value">
        <span class="score-number">{{ result.score_pct }}%</span>
        <el-progress
          :percentage="result.score_pct"
          :status="scoreStatus"
        />
      </div>
      <div class="score-details">
        <div class="score-section">
          <h5>Сильные стороны:</h5>
          <ul v-if="result.strengths && result.strengths.length">
            <li
              v-for="(strength, idx) in result.strengths"
              :key="idx"
            >
              <strong>{{ strength.metric_name }}</strong> — {{ formatValue(strength.value) }}
              (вес {{ formatValue(strength.weight, 2) }})
            </li>
          </ul>
          <el-empty
            v-else
            description="Нет данных"
            :image-size="60"
          />
        </div>
        <div class="score-section">
          <h5>Зоны развития:</h5>
          <ul v-if="result.dev_areas && result.dev_areas.length">
            <li
              v-for="(area, idx) in result.dev_areas"
              :key="idx"
            >
              <strong>{{ area.metric_name }}</strong> — {{ formatValue(area.value) }}
              (вес {{ formatValue(area.weight, 2) }})
            </li>
          </ul>
          <el-empty
            v-else
            description="Нет данных"
            :image-size="60"
          />
        </div>
      </div>
      <!-- PDF Download Button -->
      <div
        v-if="result.prof_activity_code"
        class="final-report-actions"
      >
        <el-button
          type="primary"
          size="small"
          @click="$emit('download-pdf', result)"
        >
          <el-icon><Download /></el-icon>
          Скачать PDF
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { formatFromApi } from '@/utils/numberFormat'

const props = defineProps({
  result: {
    type: Object,
    required: true
  }
})

defineEmits(['download-pdf'])

const scoreStatus = computed(() => {
  const score = props.result.score_pct
  if (score >= 70) return 'success'
  if (score >= 40) return 'warning'
  return 'exception'
})

const formatValue = (value, decimals = 1) => formatFromApi(value, decimals)
</script>

<style scoped>
.scoring-card {
  margin-bottom: 8px;
}

.scoring-card h4 {
  margin: 0 0 12px;
  color: var(--color-text-primary);
}

.scoring-result {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.score-value {
  display: flex;
  align-items: center;
  gap: 12px;
}

.score-number {
  font-size: 24px;
  font-weight: bold;
  min-width: 60px;
}

.score-details {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.score-section h5 {
  margin: 0 0 8px;
  color: var(--color-text-secondary);
}

.score-section ul {
  margin: 0;
  padding-left: 20px;
}

.score-section li {
  margin-bottom: 4px;
}

.final-report-actions {
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}

@media (max-width: 768px) {
  .score-details {
    grid-template-columns: 1fr;
  }
}
</style>
