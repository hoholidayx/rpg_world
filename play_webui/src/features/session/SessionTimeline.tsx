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
}: {
  label: string
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700"
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
  return (
    <div className="relative mt-2 flex items-center gap-1.5">
      <MiniButton label="复制" onClick={() => onCopy(message)}>
        <Copy size={14} />
      </MiniButton>
      <MiniButton label="重试" onClick={() => onRetry(message)}>
        <RotateCcw size={14} />
      </MiniButton>
      <MiniButton label="编辑" onClick={() => onEdit(message)}>
        <Pencil size={14} />
      </MiniButton>
      <MiniButton label="更多" onClick={onToggleMore}>
        <MoreHorizontal size={15} />
      </MiniButton>
      {moreOpen ? (
        <div className="absolute right-0 top-full z-20 mt-2 w-32 overflow-hidden rounded-lg border border-slate-200 bg-white p-1 shadow-xl shadow-slate-200/80">
          <button
            type="button"
            onClick={() => onDelete(message)}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm font-bold text-rose-600 transition hover:bg-rose-50"
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
    user: 'border-violet-600 bg-violet-600 text-white shadow-lg shadow-violet-100',
    assistant: 'border-slate-200 bg-white text-slate-950 shadow-sm',
    tool: 'border-sky-200 bg-sky-50 text-sky-800',
    thinking: 'border-amber-200 bg-amber-50 text-amber-800',
    error: 'border-rose-200 bg-rose-50 text-rose-700',
  }[message.role]

  if (editing) {
    return (
      <div className="rounded-lg border border-violet-200 bg-white px-3 py-3 shadow-sm">
        <textarea
          value={editDraft}
          onChange={(event) => onEditDraftChange(event.target.value)}
          className="min-h-28 w-full resize-none rounded-lg border border-slate-200 px-3 py-3 text-sm leading-7 text-slate-900 outline-none transition focus:border-violet-300"
          autoFocus
        />
        <div className="mt-3 flex justify-end gap-2">
          <button
            type="button"
            onClick={onEditCancel}
            className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold text-slate-600 transition hover:border-violet-200 hover:text-violet-700"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onEditSend}
            className="h-9 rounded-lg bg-violet-600 px-4 text-sm font-bold text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700"
          >
            发送
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className={cn('rounded-lg border px-5 py-4 text-sm leading-7', toneClass, isUser ? 'font-semibold' : '')}>
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
        <div className={cn('mb-2 flex flex-wrap items-center gap-2 text-xs font-semibold text-slate-400', isUser ? 'justify-end' : '')}>
          <span>{formatMessageTime(message.createdAt)}</span>
          <strong className="text-slate-600">
            {message.speaker.name}
            {message.speaker.label ? `（${message.speaker.label}）` : ''}
          </strong>
          {message.status ? (
            <span
              className={cn(
                'rounded-full px-2 py-0.5 text-[11px] font-black',
                message.status === 'streaming' ? 'bg-amber-50 text-amber-700' : '',
                message.status === 'done' ? 'bg-teal-50 text-teal-700' : '',
                message.status === 'local' ? 'bg-violet-50 text-violet-700' : '',
                message.status === 'error' ? 'bg-rose-50 text-rose-700' : '',
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
    <section className="min-h-0 flex-1 overflow-y-auto bg-[#f7f8fc] px-4 py-7 sm:px-6">
      <div className="mx-auto max-w-5xl">
        <div className="mb-7 flex items-center justify-center gap-4 text-xs font-bold uppercase text-slate-400">
          <span className="h-px w-24 bg-slate-200 sm:w-44" />
          时间线 / Timeline
          <span className="h-px w-24 bg-slate-200 sm:w-44" />
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
          <div className="rounded-lg border border-dashed border-slate-200 bg-white px-6 py-12 text-center">
            <h2 className="text-base font-black text-slate-950">暂无回合记录</h2>
            <p className="mt-2 text-sm font-semibold text-slate-400">发送第一条行动后，故事会从这里展开。</p>
          </div>
        )}
      </div>
    </section>
  )
}
