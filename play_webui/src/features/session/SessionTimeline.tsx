import { Copy, MoreHorizontal, Pencil, RotateCcw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { cn } from '@/lib/utils/cn'
import { SessionAvatar } from './SessionAvatar'
import { formatMessageTime } from './sessionRoomHelpers'
import type { SessionTimelineMessage } from './sessionRoomTypes'

function MiniButton({
  label,
  onClick,
  children,
  disabled = false,
}: {
  label: string
  onClick: () => void
  children: React.ReactNode
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 disabled:cursor-not-allowed disabled:border-slate-100 disabled:bg-slate-50 disabled:text-slate-300 disabled:shadow-none disabled:hover:border-slate-100 disabled:hover:bg-slate-50 disabled:hover:text-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:shadow-black/30 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200 dark:disabled:border-slate-800 dark:disabled:bg-slate-900/60 dark:disabled:text-slate-600 dark:disabled:hover:border-slate-800 dark:disabled:hover:bg-slate-900/60 dark:disabled:hover:text-slate-600"
    >
      {children}
    </button>
  )
}

function MessageActions({
  message,
  moreOpen,
  onToggleMore,
  onCopy,
  onRetry,
  onEdit,
  onDelete,
}: {
  message: SessionTimelineMessage
  moreOpen: boolean
  onToggleMore: () => void
  onCopy: (message: SessionTimelineMessage) => void
  onRetry: (message: SessionTimelineMessage) => void
  onEdit: (message: SessionTimelineMessage) => void
  onDelete: (message: SessionTimelineMessage) => void
}) {
  const canCopy = message.canCopy ?? Boolean(message.content.trim())
  const canRetry = Boolean(message.canRetry)
  const canEdit = Boolean(message.canEdit)
  const canDelete = Boolean(message.canDelete)

  return (
    <div className="relative mt-2 flex items-center gap-1.5">
      <MiniButton label="复制" disabled={!canCopy} onClick={() => onCopy(message)}>
        <Copy size={14} />
      </MiniButton>
      {canRetry ? (
        <MiniButton label="重试" onClick={() => onRetry(message)}>
          <RotateCcw size={14} />
        </MiniButton>
      ) : null}
      {canEdit ? (
        <MiniButton label="编辑" onClick={() => onEdit(message)}>
          <Pencil size={14} />
        </MiniButton>
      ) : null}
      {canDelete ? (
        <MiniButton label="更多" onClick={onToggleMore}>
          <MoreHorizontal size={15} />
        </MiniButton>
      ) : null}
      {moreOpen && canDelete ? (
        <div className="absolute right-0 top-full z-20 mt-2 w-32 overflow-hidden rounded-lg border border-slate-200 bg-white p-1 shadow-xl shadow-slate-200/80 dark:border-slate-700 dark:bg-slate-950 dark:shadow-black/40">
          <button
            type="button"
            onClick={() => onDelete(message)}
            disabled={!canDelete}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm font-bold text-rose-600 transition hover:bg-rose-50 dark:text-rose-300 dark:hover:bg-rose-500/10"
          >
            <Trash2 size={14} />
            删除
          </button>
        </div>
      ) : null}
    </div>
  )
}

function MessageBubble({
  message,
  editing,
  editDraft,
  onEditDraftChange,
  onEditCancel,
  onEditSend,
}: {
  message: SessionTimelineMessage
  editing: boolean
  editDraft: string
  onEditDraftChange: (value: string) => void
  onEditCancel: () => void
  onEditSend: () => void
}) {
  const isUser = message.role === 'user'
  const toneClass = {
    user: 'border-violet-600 bg-violet-600 text-white shadow-lg shadow-violet-100 dark:shadow-violet-950/30',
    assistant: 'border-slate-200 bg-white text-slate-950 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:shadow-black/25',
    tool: 'border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-200',
    system: 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-300',
    thinking: 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200',
    error: 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200',
  }[message.role]

  if (editing) {
    return (
      <div className="rounded-lg border border-violet-200 bg-white px-3 py-3 shadow-sm dark:border-violet-500/40 dark:bg-slate-900 dark:shadow-black/25">
        <textarea
          value={editDraft}
          onChange={(event) => onEditDraftChange(event.target.value)}
          className="min-h-28 w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-3 text-sm leading-7 text-slate-900 outline-none transition focus:border-violet-300 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-violet-500"
          autoFocus
        />
        <div className="mt-3 flex justify-end gap-2">
          <button
            type="button"
            onClick={onEditCancel}
            className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold text-slate-600 transition hover:border-violet-200 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:text-violet-200"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onEditSend}
            className="h-9 rounded-lg bg-violet-600 px-4 text-sm font-bold text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 dark:shadow-violet-950/40"
          >
            发送
          </button>
        </div>
      </div>
    )
  }

  return (
    <div
      className={cn(
        'rounded-lg border px-5 py-4 text-sm leading-7 break-words whitespace-pre-wrap',
        toneClass,
        isUser ? 'ml-auto w-fit max-w-full text-left font-semibold' : '',
      )}
    >
      {message.content || (message.status === 'streaming' ? '正在生成回应...' : '')}
    </div>
  )
}

function TimelineMessage({
  message,
  isEditing,
  editDraft,
  moreOpen,
  onToggleMore,
  onCopy,
  onRetry,
  onEdit,
  onDelete,
  onEditDraftChange,
  onEditCancel,
  onEditSend,
}: {
  message: SessionTimelineMessage
  isEditing: boolean
  editDraft: string
  moreOpen: boolean
  onToggleMore: () => void
  onCopy: (message: SessionTimelineMessage) => void
  onRetry: (message: SessionTimelineMessage) => void
  onEdit: (message: SessionTimelineMessage) => void
  onDelete: (message: SessionTimelineMessage) => void
  onEditDraftChange: (value: string) => void
  onEditCancel: () => void
  onEditSend: () => void
}) {
  const isUser = message.role === 'user'

  return (
    <article
      className={cn(
        'grid items-start gap-3',
        isUser
          ? 'ml-auto max-w-[620px] grid-cols-[minmax(0,1fr)_44px]'
          : 'max-w-[780px] grid-cols-[44px_minmax(0,1fr)]',
      )}
      data-turn-index={message.turnId}
    >
      {!isUser ? <SessionAvatar speaker={message.speaker} /> : null}
      <div className={cn('min-w-0', isUser ? 'text-right' : '')}>
        <div className={cn('mb-2 flex flex-wrap items-center gap-2 text-xs font-semibold text-slate-400 dark:text-slate-400', isUser ? 'justify-end' : '')}>
          <span>{formatMessageTime(message.createdAt)}</span>
          <strong className="text-slate-600 dark:text-slate-300">
            {message.speaker.name}
            {message.speaker.label ? `（${message.speaker.label}）` : ''}
          </strong>
          {message.status ? (
            <span
              className={cn(
                'rounded-full px-2 py-0.5 text-[11px] font-black',
                message.status === 'streaming' ? 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200' : '',
                message.status === 'done' ? 'bg-teal-50 text-teal-700 dark:bg-teal-500/15 dark:text-teal-200' : '',
                message.status === 'local' ? 'bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-200' : '',
                message.status === 'error' ? 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-200' : '',
              )}
            >
              {message.status}
            </span>
          ) : null}
        </div>
        <MessageBubble
          message={message}
          editing={isEditing}
          editDraft={editDraft}
          onEditDraftChange={onEditDraftChange}
          onEditCancel={onEditCancel}
          onEditSend={onEditSend}
        />
        {!isEditing ? (
          <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
            <MessageActions
              message={message}
              moreOpen={moreOpen}
              onToggleMore={onToggleMore}
              onCopy={onCopy}
              onRetry={onRetry}
              onEdit={onEdit}
              onDelete={onDelete}
            />
          </div>
        ) : null}
      </div>
      {isUser ? <SessionAvatar speaker={message.speaker} /> : null}
    </article>
  )
}

export function SessionTimeline({
  messages,
  editingMessageId,
  editDraft,
  onEditDraftChange,
  onCopy,
  onRetry,
  onEdit,
  onDelete,
  onEditCancel,
  onEditSend,
}: {
  messages: SessionTimelineMessage[]
  editingMessageId: string | null
  editDraft: string
  onEditDraftChange: (value: string) => void
  onCopy: (message: SessionTimelineMessage) => void
  onRetry: (message: SessionTimelineMessage) => void
  onEdit: (message: SessionTimelineMessage) => void
  onDelete: (message: SessionTimelineMessage) => void
  onEditCancel: () => void
  onEditSend: (message: SessionTimelineMessage) => void
}) {
  const [openMoreId, setOpenMoreId] = useState<string | null>(null)

  return (
    <section className="min-h-0 flex-1 overflow-y-auto bg-[#f7f8fc] px-4 py-7 dark:bg-[#0b1020] sm:px-6">
      <div className="mx-auto max-w-5xl">
        <div className="mb-7 flex items-center justify-center gap-4 text-xs font-bold uppercase text-slate-400 dark:text-slate-300">
          <span className="h-px w-24 bg-slate-200 dark:bg-slate-700 sm:w-44" />
          时间线 / Timeline
          <span className="h-px w-24 bg-slate-200 dark:bg-slate-700 sm:w-44" />
        </div>

        {messages.length ? (
          <div className="space-y-7">
            {messages.map((message) => (
              <TimelineMessage
                key={message.id}
                message={message}
                isEditing={editingMessageId === message.id}
                editDraft={editDraft}
                moreOpen={openMoreId === message.id}
                onToggleMore={() => setOpenMoreId((current) => (current === message.id ? null : message.id))}
                onCopy={onCopy}
                onRetry={onRetry}
                onEdit={onEdit}
                onDelete={(item) => {
                  setOpenMoreId(null)
                  onDelete(item)
                }}
                onEditDraftChange={onEditDraftChange}
                onEditCancel={onEditCancel}
                onEditSend={() => onEditSend(message)}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-slate-200 bg-white px-6 py-12 text-center dark:border-slate-700 dark:bg-slate-900/80">
            <h2 className="text-base font-black text-slate-950 dark:text-slate-100">暂无回合记录</h2>
            <p className="mt-2 text-sm font-semibold text-slate-400 dark:text-slate-300">发送第一条行动后，故事会从这里展开。</p>
          </div>
        )}
      </div>
    </section>
  )
}
