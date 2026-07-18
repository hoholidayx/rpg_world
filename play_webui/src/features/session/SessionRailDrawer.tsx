import { SideDrawer } from '@/components/common/SideDrawer'

export function SessionRailDrawer({
  open,
  side,
  eyebrow,
  title,
  description,
  meta,
  onClose,
  children,
}: {
  open: boolean
  side: 'left' | 'right'
  eyebrow: string
  title: string
  description?: string
  meta?: React.ReactNode
  onClose: () => void
  children: React.ReactNode
}) {
  return (
    <SideDrawer
      open={open}
      side={side}
      eyebrow={eyebrow}
      title={title}
      description={description}
      meta={meta}
      onClose={onClose}
      overlayClassName="z-[70]"
      panelClassName={side === 'left'
        ? 'lg:left-[calc(var(--session-left-rail-width)+22px)]'
        : 'lg:right-[calc(var(--session-right-rail-width)+22px)]'}
    >
      {children}
    </SideDrawer>
  )
}
