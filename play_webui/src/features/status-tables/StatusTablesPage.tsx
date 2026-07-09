'use client'

import { AppShell, useAppShell } from '@/features/layout/AppShell'
import { STATUS_TABLE_VIEW } from './constants'
import { Panel } from './components/FormBits'
import { StatusTableDialogs } from './components/StatusTableDialogs'
import { StatusTablesHeader } from './components/StatusTablesHeader'
import { useStatusTablesController } from './useStatusTablesController'
import { RuntimeTablesView } from './views/RuntimeTablesView'
import { StoryTemplatesView } from './views/StoryTemplatesView'
import { SystemTemplatesView } from './views/SystemTemplatesView'

function StatusTablesContent() {
  const { currentWorkspace } = useAppShell()
  const controller = useStatusTablesController(currentWorkspace)

  return (
    <div className="min-w-0 px-5 py-7 lg:px-8">
      <StatusTablesHeader controller={controller} />

      {controller.formError ? (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-700">
          {controller.formError}
        </div>
      ) : null}

      {!currentWorkspace ? (
        <Panel>
          <div className="px-6 py-12 text-center text-sm text-slate-500">请先选择 workspace。</div>
        </Panel>
      ) : controller.view === STATUS_TABLE_VIEW.SYSTEM ? (
        <SystemTemplatesView controller={controller} />
      ) : controller.view === STATUS_TABLE_VIEW.STORY ? (
        <StoryTemplatesView controller={controller} />
      ) : (
        <RuntimeTablesView controller={controller} />
      )}

      <StatusTableDialogs controller={controller} />
    </div>
  )
}

export function StatusTablesPage() {
  return (
    <AppShell>
      <StatusTablesContent />
    </AppShell>
  )
}
