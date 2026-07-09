import type { StatusRow, StatusTable } from '@/types/statusTables'
import { DEFAULT_KEY_COLUMN, DEFAULT_VALUE_COLUMN } from './constants'

export type TableDraft = {
  name: string
  description: string
  keyColumn: string
  valueColumn: string
  rows: StatusRow[]
}

export function createEmptyDraft(): TableDraft {
  return {
    name: '',
    description: '',
    keyColumn: DEFAULT_KEY_COLUMN,
    valueColumn: DEFAULT_VALUE_COLUMN,
    rows: [],
  }
}

export function draftFromTable(table: StatusTable | null): TableDraft {
  if (!table) return createEmptyDraft()
  return {
    name: table.name,
    description: table.description,
    keyColumn: table.keyColumn || DEFAULT_KEY_COLUMN,
    valueColumn: table.valueColumn || DEFAULT_VALUE_COLUMN,
    rows: table.rows.map((row) => ({
      key: row.key,
      value: row.value,
      runtimeKeyLocked: row.runtimeKeyLocked,
      metadata: row.metadata ?? {},
    })),
  }
}

export function validateRows(rows: StatusRow[]) {
  const seen = new Set<string>()
  const normalized: StatusRow[] = []

  for (const row of rows) {
    const key = row.key.trim()
    if (!key) return { error: 'Key 不能为空', rows: [] as StatusRow[] }
    if (seen.has(key)) return { error: `Key 不能重复：${key}`, rows: [] as StatusRow[] }
    seen.add(key)
    normalized.push({
      key,
      value: row.value,
      runtimeKeyLocked: row.runtimeKeyLocked,
      metadata: row.metadata ?? {},
    })
  }

  return { error: null, rows: normalized }
}

export function uniqueStatusTableName(baseName: string, tables: StatusTable[]) {
  const names = new Set(tables.map((table) => table.name))
  if (!names.has(baseName)) return baseName

  const firstCopy = `${baseName} 副本`
  if (!names.has(firstCopy)) return firstCopy

  for (let index = 2; index < 1000; index += 1) {
    const candidate = `${firstCopy} ${index}`
    if (!names.has(candidate)) return candidate
  }

  return `${firstCopy} ${Date.now()}`
}
