<template>
  <div class="register-container">
    <el-card class="register-card">
      <template #header>
        <div class="card-header">
          <h2>Регистрация</h2>
          <p>Создайте аккаунт для работы с системой</p>
        </div>
      </template>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="handleRegister"
        @validate="onFieldValidate"
      >
        <el-form-item
          label="ФИО"
          prop="fullName"
          :class="getFormItemClass('fullName')"
        >
          <el-input
            v-model="form.fullName"
            placeholder="Иванов Иван Иванович (необязательно)"
            size="large"
            autocomplete="name"
          />
        </el-form-item>

        <el-form-item
          label="Email"
          prop="email"
          :class="getFormItemClass('email')"
        >
          <el-input
            v-model="form.email"
            type="email"
            placeholder="Введите email"
            size="large"
            autocomplete="email"
          />
        </el-form-item>

        <el-form-item
          label="Пароль"
          prop="password"
          :class="getFormItemClass('password')"
        >
          <el-input
            v-model="form.password"
            type="password"
            placeholder="Введите пароль (минимум 8 символов, буквы и цифры)"
            size="large"
            show-password
            autocomplete="new-password"
          />
        </el-form-item>

        <el-form-item
          label="Подтверждение пароля"
          prop="confirmPassword"
          :class="getFormItemClass('confirmPassword')"
        >
          <el-input
            v-model="form.confirmPassword"
            type="password"
            placeholder="Повторите пароль"
            size="large"
            show-password
            autocomplete="new-password"
            @keyup.enter="handleRegister"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            style="width: 100%"
            :loading="authStore.loading"
            @click="handleRegister"
          >
            Зарегистрироваться
          </el-button>
        </el-form-item>

        <div
          v-if="serverErrors.length"
          :class="['auth-form-error', { 'auth-field-animate': serverErrorAnimated }]"
          role="alert"
        >
          <span
            class="auth-form-error__icon"
            aria-hidden="true"
          >
            !
          </span>
          <div class="auth-form-error__content">
            <template v-if="serverErrors.length === 1">
              {{ serverErrors[0] }}
            </template>
            <template v-else>
              <ul class="auth-form-error__list">
                <li
                  v-for="(message, index) in serverErrors"
                  :key="index"
                >
                  {{ message }}
                </li>
              </ul>
            </template>
          </div>
        </div>

        <div class="login-link">
          <span>Уже есть аккаунт?</span>
          <router-link to="/login">
            Войти
          </router-link>
        </div>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores'
import { useFieldErrorAnimation } from '@/composables/useFieldErrorAnimation'
import { normalizeApiError } from '@/utils/normalizeError'

const router = useRouter()
const authStore = useAuthStore()

const formRef = ref(null)
const form = reactive({
  fullName: '',
  email: '',
  password: '',
  confirmPassword: ''
})

const authFields = ['fullName', 'email', 'password', 'confirmPassword']

const {
  getFormItemClass,
  handleValidationErrors,
  handleFieldValidate,
  triggerForFields,
  markExternalErrors
} = useFieldErrorAnimation(authFields)

const serverErrors = ref([])
const serverErrorAnimated = ref(false)

const restartServerErrorAnimation = () => {
  serverErrorAnimated.value = false
  nextTick(() => {
    serverErrorAnimated.value = true
    setTimeout(() => {
      serverErrorAnimated.value = false
    }, 360)
  })
}

const validateConfirmPassword = (rule, value, callback) => {
  if (value === '') {
    callback(new Error('Подтвердите пароль'))
  } else if (value !== form.password) {
    callback(new Error('Пароли не совпадают'))
  } else {
    callback()
  }
}

const rules = {
  email: [
    { required: true, message: 'Введите email', trigger: 'blur' },
    { type: 'email', message: 'Некорректный email', trigger: 'blur' }
  ],
  password: [
    { required: true, message: 'Введите пароль', trigger: 'blur' },
    { min: 8, message: 'Пароль должен быть не менее 8 символов', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, validator: validateConfirmPassword, trigger: 'blur' }
  ]
}

const onFieldValidate = (prop, isValid) => {
  handleFieldValidate(prop, isValid)
  if (isValid && serverErrors.value.length) {
    serverErrors.value = []
  }
}

const handleRegister = async () => {
  if (!formRef.value) return

  serverErrors.value = []

  await formRef.value.validate(async (valid, fields) => {
    if (!valid) {
      handleValidationErrors(fields)
      return
    }

    try {
      const fullName = form.fullName.trim() || null
      await authStore.register(form.email, form.password, fullName)
      ElMessage.success({
        message: 'Регистрация успешна! Ожидайте одобрения администратора.',
        duration: 5000
      })
      router.push('/login?message=pending')
    } catch (error) {
      const normalized = error.normalizedError || normalizeApiError(error, authStore.error || 'Ошибка регистрации')
      serverErrors.value = normalized.messages
      const fieldsWithErrors = Object.keys(normalized.fieldErrors)
      const fieldsToMark = fieldsWithErrors.length ? fieldsWithErrors : authFields
      markExternalErrors(fieldsToMark)
      triggerForFields(fieldsToMark)
      restartServerErrorAnimation()
    }
  })
}

watch(
  () => [form.fullName, form.email, form.password, form.confirmPassword],
  () => {
    if (serverErrors.value.length) {
      serverErrors.value = []
    }
  }
)
</script>

<style scoped>
.register-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--color-primary-light) 0%, var(--color-bg-overlay) 100%);
  padding: 20px;
}

.register-card {
  width: 100%;
  max-width: 450px;
}

.card-header {
  text-align: center;
}

.card-header h2 {
  margin: 0 0 8px 0;
  color: var(--color-primary);
  font-size: 24px;
}

.card-header p {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: 14px;
}

.login-link {
  text-align: center;
  color: var(--color-text-secondary);
}

.login-link a {
  color: var(--color-primary);
  text-decoration: none;
  margin-left: 5px;
}

.login-link a:hover {
  text-decoration: underline;
}
</style>
