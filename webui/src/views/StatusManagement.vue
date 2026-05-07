<template>
  <div class="status-mgmt">
    <div class="main-split">
      <!-- ==================== Left: Types panel ==================== -->
      <div class="types-panel">
        <div class="panel-header">
          <h3>状态类型</h3>
          <a-button size="small" type="primary" @click="openTypeCreate">
            <template #icon><PlusOutlined /></template>
            新增
          </a-button>
        </div>
        <a-spin :spinning="typesLoading">
          <div v-if="types.length" class="type-list">
            <div
              v-for="t in types"
              :key="t"
              class="type-item"
              :class="{ active: t === selectedType }"
              @click="selectType(t)"
            >
              <FolderOutlined class="type-icon" />
              <span class="type-name">{{ t }}</span>
              <div class="type-actions" @click.stop>
                <a-button size="small" type="text" @click="openTypeRename(t)">
                  <EditOutlined />
                </a-button>
                <a-popconfirm
                  title="确定删除此类型？其下所有表格将被永久删除。"
                  @confirm="handleDeleteType(t)"
                >
                  <a-button size="small" type="text" danger>
                    <DeleteOutlined />
                  </a-button>
                </a-popconfirm>
              </div>
            </div>
          </div>
          <a-empty v-else description="暂无类型" />
        </a-spin>
      </div>

      <!-- ==================== Right: Tables list / CSV editor ==================== -->
      <div class="content-panel">
        <!-- No type selected -->
        <div v-if="!selectedType" class="placeholder">
          <a-empty description="请选择或创建一个状态类型" />
        </div>

        <!-- Type selected — show tables list -->
        <template v-else-if="!selectedTable">
          <div class="panel-header">
            <h3>
              <FolderOutlined />
              {{ selectedType }}
              <span class="table-count">（{{ tables.length }} 个表格）</span>
            </h3>
            <a-button size="small" type="primary" @click="openTableCreate">
              <template #icon><PlusOutlined /></template>
              新增表格
            </a-button>
          </div>

          <a-spin :spinning="tablesLoading">
            <div v-if="tables.length" class="table-list">
              <div
                v-for="t in tables"
                :key="t"
                class="table-item"
                @click="selectTable(t)"
              >
                <FileTextOutlined />
                <span>{{ t }}</span>
                <div class="table-actions" @click.stop>
                  <a-button size="small" type="text" @click="openTableRename(t)">
                    <EditOutlined />
                  </a-button>
                  <a-popconfirm
                    title="确定删除此表格？"
                    @confirm="handleDeleteTable(t)"
                  >
                    <a-button size="small" type="text" danger>
                      <DeleteOutlined />
                    </a-button>
                  </a-popconfirm>
                </div>
              </div>
            </div>
            <a-empty v-else description="暂无表格，点击「新增表格」创建" />
          </a-spin>
        </template>

        <!-- Table selected — CSV editor -->
        <template v-else>
          <div class="csv-editor">
            <div class="csv-breadcrumb">
              <a-button type="link" size="small" @click="backToTables">
                <LeftOutlined /> 返回
              </a-button>
              <span class="bc-sep">/</span>
              <FolderOutlined />
              <span>{{ selectedType }}</span>
              <span class="bc-sep">/</span>
              <FileTextOutlined />
              <strong>{{ selectedTable }}</strong>
            </div>

            <div class="csv-toolbar">
              <a-space>
                <a-button
                  type="primary"
                  size="small"
                  @click="saveTableData"
                  :loading="saving"
                >
                  保存
                </a-button>
                <a-button size="small" @click="addColumn">添加列</a-button>
                <a-button size="small" @click="addRow">添加行</a-button>
              </a-space>
              <span class="csv-dims">{{ localHeaders.length }} 列 × {{ localRows.length }} 行</span>
            </div>

            <div class="csv-scroll">
              <table class="csv-table" :key="selectedTable">
                <!-- Header row -->
                <thead>
                  <tr>
                    <th class="row-num">#</th>
                    <th v-for="(h, ci) in localHeaders" :key="ci" class="header-cell">
                      <div class="cell-wrap">
                        <a-input
                          v-model:value="localHeaders[ci]"
                          size="small"
                          placeholder="列名"
                        />
                        <a-button
                          size="small"
                          type="text"
                          danger
                          class="cell-remove"
                          @click="removeColumn(ci)"
                        >
                          <CloseOutlined />
                        </a-button>
                      </div>
                    </th>
                    <th class="row-num"></th>
                  </tr>
                </thead>
                <!-- Data rows -->
                <tbody>
                  <tr v-for="(row, ri) in localRows" :key="ri">
                    <td class="row-num">{{ ri + 1 }}</td>
                    <td v-for="(cell, ci) in row" :key="ci" class="data-cell">
                      <a-input v-model:value="localRows[ri][ci]" size="small" />
                    </td>
                    <td class="row-remove">
                      <a-button
                        size="small"
                        type="text"
                        danger
                        @click="removeRow(ri)"
                      >
                        <CloseOutlined />
                      </a-button>
                    </td>
                  </tr>
                </tbody>
              </table>

              <div v-if="localHeaders.length === 0" class="empty-editor">
                <a-empty description="暂无列，点击「添加列」开始编辑" />
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- ==================== Type Create/Rename Modal ==================== -->
    <a-modal
      v-model:open="typeModalVisible"
      :title="typeEditing !== null ? '重命名类型' : '新增类型'"
      :confirm-loading="typeSaving"
      @ok="handleTypeSave"
      @cancel="resetTypeForm"
      :destroy-on-close="true"
      :width="420"
    >
      <a-form ref="typeFormRef" :model="typeForm" :rules="typeRules" layout="vertical">
        <a-form-item label="类型名称" name="name">
          <a-input v-model:value="typeForm.name" placeholder="如：全局状态" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- ==================== Table Create/Rename Modal ==================== -->
    <a-modal
      v-model:open="tableModalVisible"
      :title="tableEditing !== null ? '重命名表格' : '新增表格'"
      :confirm-loading="tableSaving"
      @ok="handleTableSave"
      @cancel="resetTableForm"
      :destroy-on-close="true"
      :width="420"
    >
      <a-form ref="tableFormRef" :model="tableForm" :rules="tableRules" layout="vertical">
        <a-form-item label="表格名称" name="name">
          <a-input v-model:value="tableForm.name" placeholder="如：待完成事件" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  FolderOutlined,
  FileTextOutlined,
  LeftOutlined,
  CloseOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import {
  listTypes,
  createType,
  renameType,
  deleteType,
  listTables,
  createTable,
  getTable,
  saveTable,
  renameTable,
  deleteTable,
} from '@/api/status'

// ============================================================================
// Types
// ============================================================================

const types = ref([])
const typesLoading = ref(true)
const selectedType = ref(null)

async function loadTypes() {
  typesLoading.value = true
  try {
    types.value = await listTypes()
  } catch (e) {
    message.error('加载类型失败: ' + e.message)
  } finally {
    typesLoading.value = false
  }
}

function selectType(name) {
  selectedType.value = name
  selectedTable.value = null
  localHeaders.value = []
  localRows.value = []
  loadTables()
}

// ============================================================================
// Tables
// ============================================================================

const tables = ref([])
const tablesLoading = ref(false)
const selectedTable = ref(null)

async function loadTables() {
  if (!selectedType.value) return
  tablesLoading.value = true
  try {
    tables.value = await listTables(selectedType.value)
  } catch (e) {
    message.error('加载表格失败: ' + e.message)
  } finally {
    tablesLoading.value = false
  }
}

async function selectTable(name) {
  selectedTable.value = name
  await loadTableData(name)
}

function backToTables() {
  selectedTable.value = null
  localHeaders.value = []
  localRows.value = []
}

// ============================================================================
// CSV Editor
// ============================================================================

const localHeaders = ref([])
const localRows = ref([])
const saving = ref(false)

async function loadTableData(name) {
  try {
    const data = await getTable(selectedType.value, name)
    localHeaders.value = data.headers || []
    localRows.value = data.rows || []
  } catch (e) {
    message.error('加载表格数据失败: ' + e.message)
    localHeaders.value = []
    localRows.value = []
  }
}

async function saveTableData() {
  saving.value = true
  try {
    await saveTable(selectedType.value, selectedTable.value, {
      headers: localHeaders.value,
      rows: localRows.value,
    })
    message.success('已保存')
  } catch (e) {
    message.error('保存失败: ' + e.message)
  } finally {
    saving.value = false
  }
}

function addColumn() {
  localHeaders.value.push('')
  for (const row of localRows.value) {
    row.push('')
  }
}

function removeColumn(ci) {
  if (localHeaders.value.length <= 1) return
  localHeaders.value.splice(ci, 1)
  for (const row of localRows.value) {
    row.splice(ci, 1)
  }
}

function addRow() {
  const count = localHeaders.value.length
  localRows.value.push(new Array(count).fill(''))
}

function removeRow(ri) {
  localRows.value.splice(ri, 1)
}

// ============================================================================
// Type Modal
// ============================================================================

const typeModalVisible = ref(false)
const typeSaving = ref(false)
const typeEditing = ref(null)
const typeFormRef = ref(null)
const typeForm = reactive({ name: '' })
const typeRules = {
  name: [{ required: true, message: '请输入类型名称' }],
}

function openTypeCreate() {
  typeEditing.value = null
  typeForm.name = ''
  typeModalVisible.value = true
}

function openTypeRename(name) {
  typeEditing.value = name
  typeForm.name = name
  typeModalVisible.value = true
}

function resetTypeForm() {
  typeEditing.value = null
  typeForm.name = ''
}

async function handleTypeSave() {
  try {
    await typeFormRef.value.validate()
  } catch {
    return
  }
  typeSaving.value = true
  try {
    if (typeEditing.value) {
      await renameType(typeEditing.value, typeForm.name)
      if (selectedType.value === typeEditing.value) {
        selectedType.value = typeForm.name
      }
      message.success('已重命名')
    } else {
      await createType(typeForm.name)
      message.success('已创建')
    }
    typeModalVisible.value = false
    await loadTypes()
  } catch (e) {
    message.error('操作失败: ' + e.message)
  } finally {
    typeSaving.value = false
  }
}

async function handleDeleteType(name) {
  try {
    await deleteType(name)
    if (selectedType.value === name) {
      selectedType.value = null
      selectedTable.value = null
      localHeaders.value = []
      localRows.value = []
    }
    message.success('已删除类型')
    await loadTypes()
  } catch (e) {
    message.error('删除失败: ' + e.message)
  }
}

// ============================================================================
// Table Modal
// ============================================================================

const tableModalVisible = ref(false)
const tableSaving = ref(false)
const tableEditing = ref(null)
const tableFormRef = ref(null)
const tableForm = reactive({ name: '' })
const tableRules = {
  name: [{ required: true, message: '请输入表格名称' }],
}

function openTableCreate() {
  tableEditing.value = null
  tableForm.name = ''
  tableModalVisible.value = true
}

function openTableRename(name) {
  tableEditing.value = name
  tableForm.name = name
  tableModalVisible.value = true
}

function resetTableForm() {
  tableEditing.value = null
  tableForm.name = ''
}

async function handleTableSave() {
  try {
    await tableFormRef.value.validate()
  } catch {
    return
  }
  tableSaving.value = true
  try {
    if (tableEditing.value) {
      await renameTable(selectedType.value, tableEditing.value, tableForm.name)
      if (selectedTable.value === tableEditing.value) {
        selectedTable.value = tableForm.name
      }
      message.success('已重命名')
    } else {
      await createTable(selectedType.value, {
        name: tableForm.name,
        headers: [],
        rows: [],
      })
      message.success('已创建')
    }
    tableModalVisible.value = false
    await loadTables()
  } catch (e) {
    message.error('操作失败: ' + e.message)
  } finally {
    tableSaving.value = false
  }
}

// ============================================================================
// Lifecycle
// ============================================================================

onMounted(loadTypes)
</script>

<style scoped>
.status-mgmt {
  background: var(--card-bg);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  height: calc(100vh - 120px);
}

.main-split {
  display: flex;
  width: 100%;
  height: 100%;
}

/* ==================== Types Panel ==================== */
.types-panel {
  width: 260px;
  min-width: 260px;
  border-right: 1px solid var(--border-color, #f0f0f0);
  display: flex;
  flex-direction: column;
  background: var(--card-bg);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid var(--border-color, #f0f0f0);
}

.panel-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.type-list,
.table-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px;
}

.type-item,
.table-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}

.type-item:hover,
.table-item:hover {
  background: var(--hover-bg, rgba(0, 0, 0, 0.04));
}

.type-item.active {
  background: var(--active-bg, rgba(24, 144, 255, 0.1));
  color: var(--primary-color, #1890ff);
}

.type-icon {
  flex-shrink: 0;
}

.type-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.type-actions,
.table-actions {
  display: none;
  flex-shrink: 0;
}

.type-item:hover .type-actions,
.table-item:hover .table-actions {
  display: flex;
  gap: 2px;
}

/* ==================== Content Panel ==================== */
.content-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.table-count {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-secondary, #999);
}

/* ==================== Table List ==================== */
.table-list {
  padding: 8px;
}

.table-item {
  padding: 10px 12px;
  border: 1px solid var(--border-color, #f0f0f0);
  border-radius: 6px;
  margin-bottom: 4px;
}

.table-item:hover {
  border-color: var(--primary-color, #1890ff);
}

/* ==================== CSV Editor ==================== */
.csv-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.csv-breadcrumb {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  font-size: 13px;
  border-bottom: 1px solid var(--border-color, #f0f0f0);
  background: var(--bg-color, #fafafa);
}

.bc-sep {
  color: var(--text-tertiary, #bbb);
}

.csv-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border-color, #f0f0f0);
}

.csv-dims {
  font-size: 12px;
  color: var(--text-secondary, #999);
}

.csv-scroll {
  flex: 1;
  overflow: auto;
  padding: 8px 16px 16px;
}

.csv-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.csv-table th,
.csv-table td {
  border: 1px solid var(--border-color, #e8e8e8);
  padding: 4px;
  min-width: 100px;
  background: var(--card-bg);
}

.csv-table th.header-cell {
  background: var(--header-bg);
  position: sticky;
  top: 0;
  z-index: 1;
}

.csv-table tbody tr:nth-child(even) td.data-cell {
  background: var(--hover-bg);
}

.row-num {
  min-width: 36px !important;
  width: 36px !important;
  text-align: center;
  background: var(--header-bg, #fafafa);
  font-size: 11px;
  color: var(--text-secondary, #999);
  font-weight: 400;
}

.row-remove {
  min-width: 36px !important;
  width: 36px !important;
  text-align: center;
  padding: 2px !important;
}

.cell-wrap {
  display: flex;
  align-items: center;
  gap: 2px;
}

.cell-remove {
  flex-shrink: 0;
}

.empty-editor {
  padding: 48px 0;
  text-align: center;
}

.empty-rows {
  text-align: center;
  padding: 24px;
}
</style>
