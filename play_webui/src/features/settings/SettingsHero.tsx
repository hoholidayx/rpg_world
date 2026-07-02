export function SettingsHero() {
  return (
    <section className="relative overflow-hidden rounded-2xl bg-white px-8 py-7 shadow-sm">
      <div className="relative z-10">
        <p className="mb-2 text-sm font-semibold text-violet-600">设置后台</p>
        <h1 className="text-3xl font-bold leading-tight text-slate-950">工作区数据清理</h1>
        <p className="mt-3 max-w-2xl text-base leading-7 text-slate-500">扫描当前工作区未索引的运行目录，确认后通过 Ops 接口删除。</p>
      </div>
      <div className="absolute inset-y-0 right-0 hidden w-[42%] overflow-hidden md:block">
        <div className="absolute bottom-0 right-0 h-full w-full bg-gradient-to-l from-violet-100 via-indigo-50 to-transparent" />
        <div className="absolute bottom-0 right-12 h-28 w-80 rounded-[100%] bg-violet-200/70" />
        <div className="absolute bottom-2 right-28 h-20 w-72 rounded-[100%] bg-indigo-200/70" />
        <div className="absolute bottom-0 right-36 h-16 w-48 rounded-t-full bg-indigo-300/40" />
        <div className="absolute right-40 top-7 h-14 w-14 rounded-full bg-amber-100" />
        <div className="absolute bottom-8 right-24 h-16 w-8 rounded-t-full bg-indigo-700/80" />
        <div className="absolute bottom-7 right-20 h-4 w-16 rounded bg-indigo-700/80" />
      </div>
    </section>
  )
}
