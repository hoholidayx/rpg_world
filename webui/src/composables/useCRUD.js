import { ref, reactive, nextTick } from 'vue'
import { message } from 'ant-design-vue'

/**
 * Shared CRUD composable for CharacterManagement and LorebookManagement
 * @param {Object} options
 * @param {Function} options.listFn - API list function
 * @param {Function} options.createFn - API create function (payload)
 * @param {Function} options.updateFn - API update function (name, payload)
 * @param {Function} options.deleteFn - API delete function (name)
 * @param {string[]} [options.fixedFields] - Fields excluded from dynamicFields
 * @param {boolean} [options.hasTags] - Whether to include tag support
 * @param {string} [options.nameLabel] - Label used in validation message
 */
export function useCRUD(options) {
  const { listFn, createFn, updateFn, deleteFn, fixedFields = [], hasTags = false, nameLabel = '名称' } = options

  const items = ref([])
  const loading = ref(true)
  const modalVisible = ref(false)
  const saving = ref(false)
  const editing = ref(null)

  // Form state
  const formRef = ref(null)
  const form = reactive({
    name: '',
    enable: false,
    content: '',
    tags: [],
  })
  const dynamicFields = reactive({})

  // Tag input (only used when hasTags is true)
  const tagInputVisible = ref(false)
  const tagInput = ref('')
  const tagInputRef = ref(null)

  const rules = {
    name: [{ required: true, message: `请输入${nameLabel}` }],
  }

  // --- Data loading ---
  async function loadData() {
    loading.value = true
    try {
      items.value = await listFn()
    } catch (e) {
      message.error('加载失败: ' + e.message)
    } finally {
      loading.value = false
    }
  }

  // --- Create / Edit ---
  function openCreate() {
    editing.value = null
    form.name = ''
    form.enable = false
    form.content = ''
    form.tags = []
    // Reset extra fixed fields beyond the core set
    for (const field of fixedFields) {
      if (!['name', 'enable', 'content', 'tags'].includes(field)) {
        form[field] = ''
      }
    }
    Object.keys(dynamicFields).forEach((k) => delete dynamicFields[k])
    modalVisible.value = true
  }

  function openEdit(record) {
    editing.value = record.name
    form.name = record.name
    form.enable = !!record.enable
    form.content = record.content || ''
    form.tags = hasTags ? [...(record.tags || [])] : []

    // Populate extra fixed fields from the record
    for (const field of fixedFields) {
      if (!['name', 'enable', 'content', 'tags'].includes(field) && field in record) {
        form[field] = record[field]
      }
    }

    const fixed = new Set(fixedFields)
    Object.keys(dynamicFields).forEach((k) => delete dynamicFields[k])
    for (const [k, v] of Object.entries(record)) {
      if (!fixed.has(k)) {
        dynamicFields[k] = String(v ?? '')
      }
    }
    modalVisible.value = true
  }

  function resetForm() {
    editing.value = null
    form.name = ''
    form.enable = false
    form.content = ''
    form.tags = []
    Object.keys(dynamicFields).forEach((k) => delete dynamicFields[k])
  }

  async function handleSave() {
    try {
      await formRef.value.validate()
    } catch {
      return
    }
    saving.value = true
    try {
      const payload = {
        name: form.name,
        enable: form.enable,
        content: form.content,
      }
      if (hasTags) {
        payload.tags = form.tags
      }
      // Include extra fixed fields beyond the core set
      for (const field of fixedFields) {
        if (!['name', 'enable', 'content', 'tags'].includes(field) && field in form) {
          payload[field] = form[field]
        }
      }
      for (const [k, v] of Object.entries(dynamicFields)) {
        payload[k] = v
      }

      if (editing.value) {
        await updateFn(editing.value, payload)
        message.success('已更新')
      } else {
        await createFn(payload)
        message.success('已创建')
      }
      modalVisible.value = false
      await loadData()
    } catch (e) {
      message.error('操作失败: ' + e.message)
    } finally {
      saving.value = false
    }
  }

  // --- Delete ---
  async function handleDelete(record) {
    try {
      await deleteFn(record.name)
      message.success('已删除')
      await loadData()
    } catch (e) {
      message.error('删除失败: ' + e.message)
    }
  }

  // --- Toggle enable (with rollback on failure) ---
  async function toggleEnable(record, val) {
    const prev = record.enable
    record.enable = val
    try {
      const payload = { ...record, enable: val }
      await updateFn(record.name, payload)
      message.success(val ? '已启用' : '已禁用')
    } catch (e) {
      record.enable = prev
      message.error('操作失败: ' + e.message)
    }
  }

  // --- Tags ---
  function showTagInput() {
    tagInputVisible.value = true
    nextTick(() => {
      tagInputRef.value?.focus()
    })
  }

  function addTag() {
    const t = tagInput.value.trim()
    if (t && !form.tags.includes(t)) {
      form.tags.push(t)
    }
    tagInput.value = ''
    tagInputVisible.value = false
  }

  function removeTag(i) {
    form.tags.splice(i, 1)
  }

  // --- Dynamic fields ---
  function addField() {
    dynamicFields[`field_${Date.now()}`] = ''
  }

  function removeField(key) {
    delete dynamicFields[key]
  }

  return {
    items,
    loading,
    modalVisible,
    saving,
    editing,
    formRef,
    form,
    dynamicFields,
    rules,
    tagInputVisible,
    tagInput,
    tagInputRef,
    loadData,
    openCreate,
    openEdit,
    resetForm,
    handleSave,
    handleDelete,
    toggleEnable,
    showTagInput,
    addTag,
    removeTag,
    addField,
    removeField,
  }
}
