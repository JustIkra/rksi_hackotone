# Пакетная загрузка отчётов

## Подход

Frontend отправляет каждый файл отдельным `POST /participants/{id}/reports` запросом параллельно. Backend без изменений.

## Изменения

### Frontend: ParticipantDetailView.vue

1. **Upload Dialog** — переделать для множественной загрузки:
   - `el-upload` с `multiple`, без `:limit="1"`
   - Список выбранных файлов с индивидуальными статусами
   - Валидация: .docx, ≤20MB, макс 10 файлов
   - Кнопка "Загрузить все"

2. **Reactive State:**
```javascript
const batchFiles = ref([
  {
    id: string,           // temp UUID
    file: File,           // native File
    name: string,         // filename
    size: number,         // bytes
    status: 'pending' | 'uploading' | 'success' | 'error',
    progress: number,     // 0-100
    error: string | null,
    reportId: string | null
  }
])
```

3. **Функции:**
   - `addFiles(files)` — валидация и добавление
   - `removeFile(id)` — удаление из очереди
   - `uploadAll()` — Promise.allSettled для параллельной загрузки
   - `uploadSingleFile(item)` — загрузка одного файла

## UI

```
┌─────────────────────────────────────────────────┐
│  Загрузить отчёты                               │
├─────────────────────────────────────────────────┤
│  [Drag & Drop zone или кнопка выбора]           │
│                                                 │
│  Выбранные файлы (3/10):                        │
│  ✓ report_1.docx    2.1 MB                      │
│  ⏳ report_2.docx   1.8 MB                      │
│  ✗ report_3.docx   Ошибка: слишком большой     │
│                                                 │
│  Прогресс: 2/3                                  │
│        [Отмена]            [Загрузить все]      │
└─────────────────────────────────────────────────┘
```

## Ограничения

- Макс. 10 файлов за раз
- Макс. 20 MB на файл
- Только .docx
