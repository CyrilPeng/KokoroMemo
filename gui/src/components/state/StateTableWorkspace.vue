<script setup lang="ts">
import { computed, h } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NDropdown,
  NIcon,
  NInputNumber,
  NPopconfirm,
  NSpace,
  NTabPane,
  NTabs,
  NTag,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { AddOutline } from '@vicons/ionicons5'
import { useI18n } from 'vue-i18n'
import EditableCell from './EditableCell.vue'
import type { StateRow, StateTable } from './types'

const props = defineProps<{
  template: any | null
  tables: StateTable[]
  rowsByTable: Record<string, StateRow[]>
  recentEvents: any[]
  checkedRowKeys: string[]
  activeTableKey: string
  batchPriority: number | null
  adminToken: string
}>()

const emit = defineEmits<{
  'update:activeTableKey': [value: string]
  'update:checkedRowKeys': [value: string[]]
  'update:batchPriority': [value: number | null]
  addTab: []
  editTab: [table: StateTable]
  deleteTab: [table: StateTable]
  addRow: [table: StateTable]
  addColumn: [table: StateTable]
  editColumn: [table: StateTable, column: any]
  refreshPreview: []
  batchAction: [action: string, value?: any]
  editRow: [table: StateTable, row: StateRow]
  duplicateRow: [table: StateTable, row: StateRow]
  deleteRow: [row: StateRow]
  cellSaved: [row: StateRow, columnKey: string, value: string]
}>()

const { t } = useI18n()

const selectedCount = computed(() => props.checkedRowKeys.length)

function tableScrollX(table: StateTable) {
  return Math.max(760, table.columns.length * 180 + 430)
}

function rowClassName(row: StateRow) {
  const event = props.recentEvents.find((item: any) => item.row_id === row.row_id)
  if (!event) return ''
  if (event.event_type === 'insert_row') return 'row-inserted'
  if (event.event_type === 'update_row' || event.event_type === 'manual_cell_edit' || event.event_type === 'manual_upsert_row') return 'row-updated'
  return ''
}

function rowKey(row: StateRow) {
  return row.row_id
}

function columnsFor(table: StateTable): DataTableColumns<StateRow> {
  const valueColumns = table.columns.map((column) => ({
    title: () => h('button', {
      class: 'column-title-action',
      title: '编辑列标题',
      onClick: () => emit('editColumn', table, column),
    }, column.name),
    key: column.column_key,
    minWidth: 140,
    render: (row: StateRow) => h(EditableCell, {
      value: row.values?.[column.column_key] || '',
      rowId: row.row_id,
      columnKey: column.column_key,
      maxChars: column.max_chars || 360,
      adminToken: props.adminToken,
      onSaved: (_key: string, newValue: string) => emit('cellSaved', row, column.column_key, newValue),
    }),
  }))
  return [
    { type: 'selection', width: 48 },
    ...valueColumns,
    { title: '来源', key: 'source', width: 110, render: (row: StateRow) => h(NTag, { size: 'small' }, { default: () => row.source || 'manual' }) },
    { title: '更新时间', key: 'updated_at', width: 170, render: (row: StateRow) => row.updated_at || '-' },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (row: StateRow) => h(NSpace, { size: 6 }, {
        default: () => [
          h(NButton, { size: 'tiny', onClick: () => emit('editRow', table, row) }, { default: () => '编辑' }),
          h(NButton, { size: 'tiny', quaternary: true, onClick: () => emit('duplicateRow', table, row) }, { default: () => '复制' }),
          h(NPopconfirm, { onPositiveClick: () => emit('deleteRow', row) }, {
            trigger: () => h(NButton, { size: 'tiny', type: 'error', quaternary: true }, { default: () => '删除' }),
            default: () => '删除该状态行？',
          }),
        ],
      }),
    },
  ]
}

function tabDropdownOptions() {
  return [
    { label: '编辑标签页', key: 'edit' },
    { label: '删除标签页', key: 'delete', disabled: props.tables.length <= 1 },
  ]
}

function handleTabAction(key: string | number, table: StateTable) {
  if (key === 'edit') emit('editTab', table)
  if (key === 'delete') emit('deleteTab', table)
}
</script>

<template>
  <NCard title="状态表格">
    <NTabs
      v-if="tables.length"
      :value="activeTableKey"
      type="line"
      animated
      @update:value="emit('update:activeTableKey', String($event))"
    >
      <template #suffix>
        <NButton size="tiny" tertiary class="add-tab-inline" :disabled="!template" @click="emit('addTab')">
          <template #icon><NIcon :component="AddOutline" size="14" /></template>
          {{ t('state.template.addTab') }}
        </NButton>
      </template>
      <NTabPane v-for="table in tables" :key="table.table_key" :name="table.table_key">
        <template #tab>
          <NDropdown trigger="click" :options="tabDropdownOptions()" @select="handleTabAction($event, table)">
            <span class="tab-title-action">{{ table.name }} ({{ (rowsByTable[table.table_key] || []).length }})</span>
          </NDropdown>
        </template>
        <NSpace vertical size="medium">
          <div v-if="table.description" class="hint-text">{{ table.description }}</div>
          <NSpace align="center">
            <NButton type="primary" size="small" @click="emit('addRow', table)">
              <template #icon><NIcon :component="AddOutline" /></template>
              新增状态行
            </NButton>
            <NButton size="small" @click="emit('addColumn', table)">{{ t('state.template.addColumn') }}</NButton>
            <NButton size="small" @click="emit('refreshPreview')">刷新注入预览</NButton>
          </NSpace>
          <NSpace v-if="selectedCount" align="center" size="small" class="batch-toolbar">
            <span style="font-size: 12px; color: #a1a1aa;">{{ t('state.batch.selected', { count: selectedCount }) }}</span>
            <NInputNumber
              :value="batchPriority"
              size="small"
              :min="0"
              :max="100"
              style="width: 110px;"
              placeholder="优先级"
              @update:value="emit('update:batchPriority', $event)"
            />
            <NButton size="tiny" quaternary :disabled="batchPriority == null" @click="emit('batchAction', 'set_priority', batchPriority)">设优先级</NButton>
            <NPopconfirm @positive-click="emit('batchAction', 'delete')">
              <template #trigger><NButton size="tiny" type="error" quaternary>{{ t('state.batch.deleteSelected') }}</NButton></template>
              {{ t('state.batch.deleteConfirm', { count: selectedCount }) }}
            </NPopconfirm>
            <NButton size="tiny" quaternary @click="emit('update:checkedRowKeys', [])">{{ t('state.batch.clearSelection') }}</NButton>
          </NSpace>
          <NDataTable
            class="state-data-table"
            :columns="columnsFor(table)"
            :data="rowsByTable[table.table_key] || []"
            :pagination="{ pageSize: 8 }"
            :scroll-x="tableScrollX(table)"
            :row-class-name="rowClassName"
            :row-key="rowKey"
            :checked-row-keys="checkedRowKeys"
            @update:checked-row-keys="emit('update:checkedRowKeys', $event as string[])"
          />
        </NSpace>
      </NTabPane>
    </NTabs>
    <NAlert v-else type="warning">暂无表格模板，请先确认后端数据库初始化正常。</NAlert>
  </NCard>
</template>

<style scoped>
.state-data-table {
  width: 100%;
}

.add-tab-inline {
  margin-top: 2px;
}

.state-data-table :deep(.n-data-table-base-table-body) {
  overflow-x: auto;
}

.hint-text {
  color: #a1a1aa;
  font-size: 12px;
  line-height: 1.6;
  margin: 4px 0 0 0;
}

.batch-toolbar {
  padding: 6px 10px;
  background: #1a1a2e;
  border-radius: 4px;
}

.tab-title-action {
  cursor: pointer;
}

.column-title-action {
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

.column-title-action:hover,
.tab-title-action:hover {
  color: #63e2b7;
}
</style>
