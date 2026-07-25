'use client'

import { Sparkles } from 'lucide-react'
import {
  MEDIA_ASPECT_RATIOS,
  type VisualBrief,
} from '@/types/media'

export function VisualBriefEditor({
  value,
  disabled,
  onChange,
}: {
  value: VisualBrief
  disabled: boolean
  onChange: (next: VisualBrief) => void
}) {
  const set = <Key extends keyof VisualBrief,>(
    key: Key,
    fieldValue: VisualBrief[Key],
  ) => {
    onChange({ ...value, [key]: fieldValue })
  }
  const textFields: Array<{
    key: Exclude<
      keyof VisualBrief,
      'subjects' | 'aspectRatio' | 'userPrompt'
    >
    label: string
    rows?: number
  }> = [
    { key: 'sceneDescription', label: '场景描述', rows: 4 },
    { key: 'environment', label: '环境' },
    { key: 'action', label: '动作' },
    { key: 'composition', label: '构图' },
    { key: 'moodLighting', label: '氛围与光线' },
    { key: 'style', label: '视觉风格' },
    { key: 'negativeConstraints', label: '负面约束', rows: 2 },
  ]

  return (
    <div className="space-y-3">
      {textFields.map((field) => (
        <label
          key={field.key}
          className="block text-xs font-black text-slate-600 dark:text-slate-300"
        >
          {field.label}
          <textarea
            value={value[field.key]}
            rows={field.rows ?? 2}
            disabled={disabled}
            onChange={(event) => set(field.key, event.target.value)}
            className="mt-1.5 w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold leading-5 text-slate-800 outline-none transition focus:border-violet-400 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
          />
        </label>
      ))}
      <label className="block text-xs font-black text-slate-600 dark:text-slate-300">
        主体（逗号分隔）
        <input
          value={value.subjects.join(', ')}
          disabled={disabled}
          onChange={(event) => set(
            'subjects',
            event.target.value
              .split(',')
              .map((item) => item.trim())
              .filter(Boolean),
          )}
          className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-800 outline-none transition focus:border-violet-400 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
        />
      </label>
      <label className="block text-xs font-black text-slate-600 dark:text-slate-300">
        画幅
        <select
          value={value.aspectRatio}
          disabled={disabled}
          onChange={(event) => set(
            'aspectRatio',
            event.target.value as VisualBrief['aspectRatio'],
          )}
          className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-black text-slate-800 outline-none disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
        >
          {MEDIA_ASPECT_RATIOS.map((ratio) => (
            <option key={ratio} value={ratio}>{ratio}</option>
          ))}
        </select>
      </label>
      <label className="block rounded-xl border border-violet-200 bg-violet-50/80 p-3 text-xs font-black text-violet-800 dark:border-violet-500/30 dark:bg-violet-500/10 dark:text-violet-200">
        <span className="flex items-center gap-2">
          <Sparkles size={14} />
          你的最高优先级要求
        </span>
        <textarea
          value={value.userPrompt}
          rows={4}
          disabled={disabled}
          placeholder="例如：必须保持角色黑色短发与金色眼睛；画面重点表现两人雨中对视。"
          onChange={(event) => set('userPrompt', event.target.value)}
          className="mt-2 w-full resize-y rounded-lg border border-violet-200 bg-white px-3 py-2 text-sm font-semibold leading-5 text-slate-800 outline-none transition focus:border-violet-500 disabled:opacity-60 dark:border-violet-500/30 dark:bg-slate-950 dark:text-slate-100"
        />
        <span className="mt-2 block font-semibold leading-5 text-violet-600 dark:text-violet-300">
          这段内容会放在最终提示词末尾，并覆盖上方冲突的画面语义；Provider
          安全规则和画幅、尺寸等硬参数不受影响。
        </span>
      </label>
    </div>
  )
}
