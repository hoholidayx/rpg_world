'use client'

import { Fragment, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, RefreshCw } from 'lucide-react'
import { getContextPreview } from '@/lib/api/contextPreview'
import { listSessions } from '@/lib/api/sessions'
import { listStories } from '@/lib/api/stories'
import { HISTORY_MESSAGE_ROLE } from '@/types/session'
import type { ContextPreviewLayer, ContextPreviewPayload } from '@/types/contextPreview'

type PreviewView = 'layer' | 'messages' | 'json'

const layerLabels: Record<string, string> = {
  fixed_layer: 'Fixed Layer',
  persistent_memory: 'Persistent Memory',
  summary: 'Summary',
  hot_history: 'Hot History',
  story_memory: 'Story Memory',
  recalled_memory: 'Recalled Memory',
  status_tables: 'Status Tables',
  rp_modules: 'RP Modules',
  user_message: 'User Message',
}

function formatNumber(value: number | null | undefined) {
  if (typeof value !== 'number') return '-'
  return value.toLocaleString('en-US')
}

function layerLabel(type: string) {
  return layerLabels[type] ?? type
}

function queryErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : '请求失败'
}

function roleBadgeClass(role: string) {
  if (role === HISTORY_MESSAGE_ROLE.USER) return 'bg-teal-50 text-teal-700 ring-teal-100'
  if (role === HISTORY_MESSAGE_ROLE.ASSISTANT) return 'bg-amber-50 text-amber-700 ring-amber-100'
  if (role === HISTORY_MESSAGE_ROLE.TOOL) return 'bg-rose-50 text-rose-700 ring-rose-100'
  return 'bg-sky-50 text-sky-700 ring-sky-100'
}

function normalizeMessageMarkdown(value: string) {
  return value
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replace(/\\n/g, '\n')
}

function isTableRow(line: string) {
  return /^\|.+\|$/.test(line.trim())
}

function isTableSeparator(line: string) {
  return /^\|?[\s:-]+\|[\s|:-]*$/.test(line.trim())
}

function isTableStart(lines: string[], index: number) {
  return isTableRow(lines[index]) && index + 1 < lines.length && isTableSeparator(lines[index + 1])
}

function splitTableRow(row: string) {
  return row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim())
}

function bracketTagName(line: string) {
  const match = line.trim().match(/^\[([A-Za-z][A-Za-z0-9_-]*)\]$/)
  return match?.[1] ?? null
}

function isBracketClose(line: string, tagName: string) {
  return line.trim() === `[/${tagName}]`
}

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g).filter(Boolean)
  return parts.map((part, index) => {
    const key = `${keyPrefix}-${index}`
    if (part.startsWith('`') && part.endsWith('`') && part.length > 1) {
      return (
        <code key={key} className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[12px] text-slate-700">
          {part.slice(1, -1)}
        </code>
      )
    }
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={key}>{part.slice(2, -2)}</strong>
    }
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
      return <em key={key}>{part.slice(1, -1)}</em>
    }
    return <Fragment key={key}>{part}</Fragment>
  })
}

function renderTable(rows: string[], key: string) {
  const normalizedRows = rows.filter((row) => !isTableSeparator(row))
  const cells = normalizedRows.map(splitTableRow)
  if (!cells.length) return null
  const [head, ...body] = cells

  return (
    <div key={key} className="mb-3 overflow-x-auto">
      <table className="w-full border-collapse text-left text-xs">
        <thead>
          <tr>
            {head.map((cell, index) => (
              <th key={`${key}-head-${index}`} className="border border-slate-200 bg-slate-50 px-2 py-1.5 font-bold text-slate-700">
                {renderInline(cell, `${key}-head-${index}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, rowIndex) => (
            <tr key={`${key}-row-${rowIndex}`}>
              {row.map((cell, cellIndex) => (
                <td key={`${key}-cell-${rowIndex}-${cellIndex}`} className="border border-slate-200 px-2 py-1.5 align-top text-slate-700">
                  {renderInline(cell, `${key}-cell-${rowIndex}-${cellIndex}`)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function collectTableRows(lines: string[], startIndex: number) {
  const rows = [lines[startIndex], lines[startIndex + 1]]
  let index = startIndex + 2

  while (index < lines.length) {
    const line = lines[index]
    if (isTableRow(line)) {
      rows.push(line)
      index += 1
      continue
    }

    if (!line.trim()) {
      let nextIndex = index + 1
      while (nextIndex < lines.length && !lines[nextIndex].trim()) {
        nextIndex += 1
      }
      if (nextIndex < lines.length && isTableRow(lines[nextIndex])) {
        index = nextIndex
        continue
      }
    }

    break
  }

  return { rows, nextIndex: index }
}

function collectBracketBlock(lines: string[], startIndex: number, tagName: string) {
  const innerLines: string[] = []
  let index = startIndex + 1

  while (index < lines.length) {
    if (isBracketClose(lines[index], tagName)) {
      return { innerLines, nextIndex: index + 1 }
    }
    innerLines.push(lines[index])
    index += 1
  }

  return null
}

function renderBracketBlock(tagName: string, innerLines: string[], key: string) {
  return (
    <section key={key} className="mb-3 overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
      <div className="border-b border-slate-200 bg-white px-3 py-2">
        <span className="inline-flex h-6 items-center rounded-full border border-indigo-100 bg-indigo-50 px-2.5 font-mono text-[11px] font-bold text-indigo-700">
          {tagName}
        </span>
      </div>
      <div className="px-3 py-3">
        {renderMarkdownBlocks(innerLines.join('\n'))}
      </div>
    </section>
  )
}

function renderMarkdownBlocks(content: string): ReactNode {
  const lines = normalizeMessageMarkdown(content).split('\n')
  const blocks: ReactNode[] = []
  let paragraph: string[] = []
  let blockIndex = 0

  function flushParagraph() {
    if (!paragraph.length) return
    const key = `p-${blockIndex}`
    blocks.push(
      <p key={key} className="mb-2.5 text-sm leading-7 text-slate-700">
        {renderInline(paragraph.join(' '), key)}
      </p>,
    )
    paragraph = []
    blockIndex += 1
  }

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]
    const trimmed = line.trim()

    if (!trimmed) {
      flushParagraph()
      continue
    }

    const tagName = bracketTagName(trimmed)
    if (tagName) {
      const block = collectBracketBlock(lines, index, tagName)
      if (block) {
        flushParagraph()
        const key = `bracket-${blockIndex}`
        blocks.push(renderBracketBlock(tagName, block.innerLines, key))
        blockIndex += 1
        index = block.nextIndex - 1
        continue
      }
    }

    if (trimmed.startsWith('```')) {
      flushParagraph()
      const codeLines: string[] = []
      index += 1
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        codeLines.push(lines[index])
        index += 1
      }
      blocks.push(
        <pre key={`code-${blockIndex}`} className="mb-3 max-h-64 overflow-auto rounded-lg bg-slate-950 px-3 py-2.5 text-xs leading-6 text-slate-100">
          <code>{codeLines.join('\n')}</code>
        </pre>,
      )
      blockIndex += 1
      continue
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/)
    if (heading) {
      flushParagraph()
      const level = heading[1].length
      const className = level === 1
        ? 'mb-2 mt-3 text-base font-bold text-slate-950'
        : 'mb-2 mt-3 text-sm font-bold text-slate-950'
      blocks.push(
        <h3 key={`h-${blockIndex}`} className={className}>
          {renderInline(heading[2], `h-${blockIndex}`)}
        </h3>,
      )
      blockIndex += 1
      continue
    }

    if (isTableStart(lines, index)) {
      flushParagraph()
      const tableBlock = collectTableRows(lines, index)
      index = tableBlock.nextIndex - 1
      const table = renderTable(tableBlock.rows, `table-${blockIndex}`)
      if (table) blocks.push(table)
      blockIndex += 1
      continue
    }

    if (/^[-*]\s+/.test(trimmed)) {
      flushParagraph()
      const items: string[] = []
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ''))
        index += 1
      }
      index -= 1
      blocks.push(
        <ul key={`ul-${blockIndex}`} className="mb-3 list-disc space-y-1 pl-5 text-sm leading-6 text-slate-700">
          {items.map((item, itemIndex) => (
            <li key={`li-${blockIndex}-${itemIndex}`}>{renderInline(item, `li-${blockIndex}-${itemIndex}`)}</li>
          ))}
        </ul>,
      )
      blockIndex += 1
      continue
    }

    paragraph.push(trimmed)
  }

  flushParagraph()
  return blocks.length ? blocks : <p className="text-sm text-slate-400">(empty)</p>
}

function MarkdownContent({ content }: { content: string }) {
  return <div className="min-w-0 break-words">{renderMarkdownBlocks(content)}</div>
}

function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="flex min-h-[420px] items-center justify-center px-6 py-12 text-center">
      <div>
        <p className="text-sm font-bold text-slate-700">{title}</p>
        {detail ? <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">{detail}</p> : null}
      </div>
    </div>
  )
}

function selectedLayerOrNull(preview: ContextPreviewPayload | undefined, index: number) {
  if (!preview?.layers.length) return null
  return preview.layers[index] ?? preview.layers[0]
}

function previewUnavailableMessage({
  workspaceId,
  storiesLoading,
  storiesError,
  storiesCount,
  sessionsLoading,
  sessionsError,
  sessionsCount,
  previewLoading,
  previewError,
}: {
  workspaceId: string | null
  storiesLoading: boolean
  storiesError: unknown
  storiesCount: number
  sessionsLoading: boolean
  sessionsError: unknown
  sessionsCount: number
  previewLoading: boolean
  previewError: unknown
}) {
  if (!workspaceId) return { title: '暂无 workspace', detail: '请先在顶部选择一个 workspace。' }
  if (storiesLoading) return { title: '正在读取故事', detail: '读取完成后会自动选择第一个故事。' }
  if (storiesError) return { title: '故事加载失败', detail: queryErrorMessage(storiesError) }
  if (storiesCount === 0) return { title: '当前 workspace 暂无故事', detail: '创建故事和会话后可预览上下文。' }
  if (sessionsLoading) return { title: '正在读取会话', detail: '读取完成后会自动选择第一个会话。' }
  if (sessionsError) return { title: '会话加载失败', detail: queryErrorMessage(sessionsError) }
  if (sessionsCount === 0) return { title: '当前故事暂无会话', detail: '创建会话后可查看该 session 的 context-preview payload。' }
  if (previewLoading) return { title: '正在加载上下文预览', detail: '正在从 Play API 读取 context-preview.v1 payload。' }
  if (previewError) return { title: '上下文预览加载失败', detail: queryErrorMessage(previewError) }
  return { title: '暂无上下文预览', detail: '请选择故事和会话。' }
}

function LayerList({
  layers,
  selectedIndex,
  onSelect,
}: {
  layers: ContextPreviewLayer[]
  selectedIndex: number
  onSelect: (index: number) => void
}) {
  if (!layers.length) {
    return <div className="px-4 py-10 text-center text-sm font-semibold text-slate-400">暂无 layer</div>
  }

  return (
    <div className="grid">
      {layers.map((layer, index) => {
        const selected = index === selectedIndex
        const inactive = layer.status !== 'active'
        return (
          <button
            key={`${layer.type}-${index}`}
            type="button"
            onClick={() => onSelect(index)}
            className={`border-b border-slate-200 px-4 py-3 text-left transition ${
              selected ? 'bg-indigo-50 shadow-[inset_3px_0_0_#4f46e5]' : 'bg-transparent hover:bg-slate-50'
            } ${inactive ? 'text-slate-400' : 'text-slate-900'}`}
          >
            <span className="flex items-center justify-between gap-3">
              <span className="truncate text-sm font-bold">{layerLabel(layer.type)}</span>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 font-mono text-[11px] font-bold text-slate-600">{layer.role}</span>
            </span>
            <span className="mt-2 flex items-center gap-2 text-xs font-semibold text-slate-500">
              <span className={`h-1.5 w-1.5 rounded-full ${inactive ? 'bg-slate-300' : 'bg-emerald-500'}`} />
              <span>{layer.status}</span>
              <span>{formatNumber(layer.tokenCount)} tokens</span>
            </span>
          </button>
        )
      })}
    </div>
  )
}

function PreviewViewer({
  preview,
  selectedLayer,
  view,
}: {
  preview: ContextPreviewPayload
  selectedLayer: ContextPreviewLayer | null
  view: PreviewView
}) {
  if (view === 'messages') {
    if (!preview.messages.length) {
      return <EmptyState title="暂无 messages" detail="当前 context payload 没有最终 LLM message 列表。" />
    }
    return (
      <div className="max-h-[560px] space-y-3 overflow-auto pr-1">
        {preview.messages.map((message, index) => (
          <article key={`message-${index}`} className="grid gap-3 rounded-lg border border-slate-200 bg-white p-3 shadow-sm sm:grid-cols-[92px_minmax(0,1fr)]">
            <span className={`flex h-7 items-center justify-center rounded-full text-xs font-bold ring-1 ${roleBadgeClass(message.role)}`}>
              {message.role}
            </span>
            <MarkdownContent content={String(message.content ?? '')} />
          </article>
        ))}
      </div>
    )
  }

  const content = view === 'json'
    ? JSON.stringify(preview, null, 2)
    : selectedLayer?.content ?? ''

  return (
    <pre className="max-h-[560px] min-h-[420px] overflow-auto whitespace-pre-wrap break-words rounded-lg border border-slate-200 bg-slate-950 p-4 font-mono text-xs leading-6 text-slate-100">
      {content}
    </pre>
  )
}

export function ContextPreviewSettingsContainer({ workspaceId }: { workspaceId: string | null }) {
  const queryClient = useQueryClient()
  const [selectedStoryId, setSelectedStoryId] = useState<number | null>(null)
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [selectedLayerIndex, setSelectedLayerIndex] = useState(0)
  const [view, setView] = useState<PreviewView>('layer')

  const storiesQuery = useQuery({
    queryKey: ['play-context-preview-stories', workspaceId],
    queryFn: () => listStories(workspaceId ?? ''),
    enabled: Boolean(workspaceId),
  })
  const stories = useMemo(() => storiesQuery.data ?? [], [storiesQuery.data])
  const selectedStory = selectedStoryId ? stories.find((story) => story.id === selectedStoryId) ?? null : null

  const sessionsQuery = useQuery({
    queryKey: ['play-context-preview-sessions', workspaceId, selectedStoryId],
    queryFn: () => listSessions(workspaceId ?? '', selectedStoryId ?? 0),
    enabled: Boolean(workspaceId && selectedStoryId),
  })
  const sessions = useMemo(() => sessionsQuery.data ?? [], [sessionsQuery.data])
  const selectedSession = selectedSessionId ? sessions.find((session) => session.id === selectedSessionId) ?? null : null

  const previewQuery = useQuery({
    queryKey: ['play-context-preview', selectedSessionId],
    queryFn: () => getContextPreview(selectedSessionId ?? ''),
    enabled: Boolean(selectedSessionId),
  })

  const preview = previewQuery.data
  const selectedLayer = selectedLayerOrNull(preview, selectedLayerIndex)

  useEffect(() => {
    setSelectedStoryId(null)
    setSelectedSessionId(null)
    setSelectedLayerIndex(0)
    setView('layer')
  }, [workspaceId])

  useEffect(() => {
    if (!workspaceId || !storiesQuery.isSuccess) return
    if (!stories.length) {
      setSelectedStoryId(null)
      return
    }
    if (!selectedStoryId || !stories.some((story) => story.id === selectedStoryId)) {
      setSelectedStoryId(stories[0].id)
    }
  }, [selectedStoryId, stories, storiesQuery.isSuccess, workspaceId])

  useEffect(() => {
    setSelectedSessionId(null)
    setSelectedLayerIndex(0)
    setView('layer')
  }, [selectedStoryId])

  useEffect(() => {
    if (!workspaceId || !selectedStoryId || !sessionsQuery.isSuccess) return
    if (!sessions.length) {
      setSelectedSessionId(null)
      return
    }
    if (!selectedSessionId || !sessions.some((session) => session.id === selectedSessionId)) {
      setSelectedSessionId(sessions[0].id)
    }
  }, [selectedSessionId, selectedStoryId, sessions, sessionsQuery.isSuccess, workspaceId])

  useEffect(() => {
    setSelectedLayerIndex(0)
    setView('layer')
  }, [selectedSessionId])

  useEffect(() => {
    if (preview?.layers.length && selectedLayerIndex >= preview.layers.length) {
      setSelectedLayerIndex(0)
    }
  }, [preview?.layers.length, selectedLayerIndex])

  const unavailable = !preview
    ? previewUnavailableMessage({
      workspaceId,
      storiesLoading: storiesQuery.isLoading,
      storiesError: storiesQuery.error,
      storiesCount: stories.length,
      sessionsLoading: sessionsQuery.isLoading,
      sessionsError: sessionsQuery.error,
      sessionsCount: sessions.length,
      previewLoading: previewQuery.isLoading,
      previewError: previewQuery.error,
    })
    : null

  function refreshPreview() {
    if (!selectedSessionId) return
    void queryClient.invalidateQueries({ queryKey: ['play-context-preview', selectedSessionId] })
  }

  return (
    <section className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="grid gap-5 border-b border-slate-200 bg-gradient-to-b from-white to-slate-50 px-5 py-5 lg:grid-cols-[minmax(0,1fr)_auto]">
        <div>
          <p className="mb-2 flex items-center gap-2 text-sm font-bold text-slate-500">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            设置 / 调试
          </p>
          <h2 className="text-2xl font-bold text-slate-950">上下文预览</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">选择故事和会话后查看当前渲染上下文，用于核对进入 LLM 边界的 layers 与 messages。</p>
        </div>
        <div className="flex flex-wrap gap-2 lg:justify-end">
          <span className="flex h-7 items-center rounded-full border border-indigo-100 bg-indigo-50 px-3 text-xs font-bold text-indigo-700">
            {preview?.formatVersion ?? 'context-preview.v1'}
          </span>
          <span className="flex h-7 items-center rounded-full border border-teal-100 bg-teal-50 px-3 text-xs font-bold text-teal-700">
            {preview?.sessionId ?? selectedSessionId ?? 'no session'}
          </span>
        </div>
      </header>

      <div className="grid gap-3 border-b border-slate-200 px-5 py-4 lg:grid-cols-[minmax(220px,1fr)_minmax(220px,1fr)_auto] lg:items-end">
        <label className="min-w-0">
          <span className="mb-2 flex justify-between gap-3 text-xs font-bold text-slate-500">
            <span>故事</span>
            <span>workspace / story</span>
          </span>
          <select
            value={selectedStoryId ?? ''}
            onChange={(event) => {
              const rawValue = event.target.value
              const nextId = Number(rawValue)
              setSelectedStoryId(rawValue && Number.isFinite(nextId) ? nextId : null)
            }}
            disabled={!workspaceId || storiesQuery.isLoading || stories.length === 0}
            className="h-11 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-semibold text-slate-900 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100 disabled:cursor-not-allowed disabled:text-slate-400"
          >
            <option value="">{storiesQuery.isLoading ? '故事加载中' : '请选择故事'}</option>
            {stories.map((story) => (
              <option key={story.id} value={story.id}>{story.title}</option>
            ))}
          </select>
        </label>

        <label className="min-w-0">
          <span className="mb-2 flex justify-between gap-3 text-xs font-bold text-slate-500">
            <span>会话</span>
            <span>global session_id</span>
          </span>
          <select
            value={selectedSessionId ?? ''}
            onChange={(event) => setSelectedSessionId(event.target.value || null)}
            disabled={!selectedStoryId || sessionsQuery.isLoading || sessions.length === 0}
            className="h-11 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-semibold text-slate-900 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100 disabled:cursor-not-allowed disabled:text-slate-400"
          >
            <option value="">{sessionsQuery.isLoading ? '会话加载中' : '请选择会话'}</option>
            {sessions.map((session) => (
              <option key={session.id} value={session.id}>{session.title || session.id}</option>
            ))}
          </select>
        </label>

        <button
          type="button"
          onClick={refreshPreview}
          disabled={!selectedSessionId || previewQuery.isFetching}
          className="flex h-11 items-center justify-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-bold text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {previewQuery.isFetching ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
          刷新预览
        </button>
      </div>

      <div className="grid border-b border-slate-200 bg-slate-50 md:grid-cols-4">
        <div className="border-b border-slate-200 px-4 py-4 md:border-b-0 md:border-r">
          <span className="text-xs font-bold text-slate-500">主上下文估算 token</span>
          <strong className="mt-2 block text-2xl font-bold text-slate-950">{formatNumber(preview?.totals.tokenCount)}</strong>
          <em className="mt-1 block text-xs font-semibold not-italic text-slate-400">历史窗口 {preview?.hotHistoryRounds ?? '-'} 轮，不含子 Agent</em>
        </div>
        <div className="border-b border-slate-200 px-4 py-4 md:border-b-0 md:border-r">
          <span className="text-xs font-bold text-slate-500">活跃层</span>
          <strong className="mt-2 block text-2xl font-bold text-slate-950">{preview ? `${preview.totals.activeLayers} / ${preview.totals.layerCount}` : '-'}</strong>
          <em className="mt-1 block text-xs font-semibold not-italic text-slate-400">layers</em>
        </div>
        <div className="border-b border-slate-200 px-4 py-4 md:border-b-0 md:border-r">
          <span className="text-xs font-bold text-slate-500">Messages</span>
          <strong className="mt-2 block text-2xl font-bold text-slate-950">{formatNumber(preview?.totals.messageCount)}</strong>
          <em className="mt-1 block text-xs font-semibold not-italic text-slate-400">final boundary</em>
        </div>
        <div className="px-4 py-4">
          <span className="text-xs font-bold text-slate-500">选中层估算 token</span>
          <strong className="mt-2 block text-2xl font-bold text-slate-950">{formatNumber(selectedLayer?.tokenCount)}</strong>
          <em className="mt-1 block truncate text-xs font-semibold not-italic text-slate-400">{selectedLayer?.type ?? '-'}</em>
        </div>
      </div>

      <div className="grid min-h-[620px] lg:grid-cols-[minmax(270px,330px)_minmax(0,1fr)]">
        <aside className="border-b border-slate-200 bg-slate-50/70 lg:border-b-0 lg:border-r">
          <div className="flex h-14 items-center justify-between gap-3 border-b border-slate-200 px-4">
            <h3 className="text-sm font-bold text-slate-950">Context Layers</h3>
            <span className="text-xs font-bold text-slate-500">{preview?.layers.length ?? 0} layers</span>
          </div>
          <LayerList layers={preview?.layers ?? []} selectedIndex={selectedLayerIndex} onSelect={setSelectedLayerIndex} />
        </aside>

        <section className="min-w-0 bg-white">
          <div className="grid min-h-14 gap-3 border-b border-slate-200 px-4 py-2 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
            <div className="min-w-0">
              <strong className="block truncate text-sm font-bold text-slate-950">{selectedLayer ? layerLabel(selectedLayer.type) : selectedStory?.title ?? '上下文预览'}</strong>
              <span className="mt-1 block truncate text-xs font-semibold text-slate-500">{selectedLayer?.description ?? selectedSession?.title ?? '请选择故事和会话'}</span>
            </div>
            <nav className="flex rounded-lg border border-slate-200 bg-slate-50 p-1" aria-label="预览模式">
              {(['layer', 'messages', 'json'] as const).map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setView(item)}
                  disabled={!preview}
                  className={`h-8 flex-1 rounded-md px-3 text-xs font-bold transition lg:flex-none ${
                    view === item ? 'bg-slate-950 text-white' : 'text-slate-500 hover:bg-white hover:text-slate-900'
                  } disabled:cursor-not-allowed disabled:opacity-50`}
                >
                  {item === 'layer' ? 'Layer' : item === 'messages' ? 'Messages' : 'JSON'}
                </button>
              ))}
            </nav>
          </div>

          <div className="grid border-b border-slate-200 bg-slate-50 md:grid-cols-3">
            <div className="border-b border-slate-200 px-4 py-3 md:border-b-0 md:border-r">
              <span className="block text-[11px] font-bold uppercase text-slate-500">role</span>
              <strong className="mt-1 block truncate font-mono text-xs text-slate-900">{selectedLayer?.role ?? '-'}</strong>
            </div>
            <div className="border-b border-slate-200 px-4 py-3 md:border-b-0 md:border-r">
              <span className="block text-[11px] font-bold uppercase text-slate-500">status</span>
              <strong className="mt-1 block truncate font-mono text-xs text-slate-900">{selectedLayer?.status ?? '-'}</strong>
            </div>
            <div className="px-4 py-3">
              <span className="block text-[11px] font-bold uppercase text-slate-500">chars / tokens</span>
              <strong className="mt-1 block truncate font-mono text-xs text-slate-900">
                {selectedLayer ? `${formatNumber(selectedLayer.charCount)} / ${formatNumber(selectedLayer.tokenCount)}` : '-'}
              </strong>
            </div>
          </div>

          <div className="bg-slate-50 p-4">
            {preview ? <PreviewViewer preview={preview} selectedLayer={selectedLayer} view={view} /> : <EmptyState title={unavailable?.title ?? '暂无上下文预览'} detail={unavailable?.detail} />}
          </div>
        </section>
      </div>
    </section>
  )
}
