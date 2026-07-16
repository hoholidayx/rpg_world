import type { CSSProperties, ReactNode } from 'react'
import { cn } from '@/lib/utils/cn'

export function MediaImageFrame({
  src,
  alt,
  className,
  style,
  loading = 'lazy',
  decorative = false,
  children,
}: {
  src: string
  alt: string
  className?: string
  style?: CSSProperties
  loading?: 'eager' | 'lazy'
  decorative?: boolean
  children?: ReactNode
}) {
  return (
    <div className={cn('relative overflow-hidden bg-slate-950', className)} style={style}>
      <img
        src={src}
        alt=""
        aria-hidden="true"
        loading={loading}
        decoding="async"
        className="pointer-events-none absolute inset-0 h-full w-full scale-110 select-none object-cover object-center opacity-70 blur-xl"
      />
      <img
        src={src}
        alt={decorative ? '' : alt}
        aria-hidden={decorative ? 'true' : undefined}
        loading={loading}
        decoding="async"
        className="pointer-events-none absolute inset-0 h-full w-full select-none object-contain object-center"
      />
      {children}
    </div>
  )
}
