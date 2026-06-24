import type { Scene } from '@/types/scene'

export function SceneHud({ scene }: { scene?: Scene }) {
  return (
    <aside className="rounded-3xl border border-white/10 bg-panel/80 p-5 shadow-2xl">
      <h2 className="text-lg font-semibold">当前场景</h2>
      <dl className="mt-4 space-y-3 text-sm text-muted">
        <div><dt className="text-white">地点</dt><dd>{scene?.location ?? '未设定地点'}</dd></div>
        <div><dt className="text-white">时间</dt><dd>{scene?.time ?? '未知时间'}</dd></div>
        <div><dt className="text-white">氛围</dt><dd>{scene?.mood ?? '待展开'}</dd></div>
        <div><dt className="text-white">在场角色</dt><dd>{scene?.presentCharacters?.join('、') || '暂无'}</dd></div>
      </dl>
    </aside>
  )
}
