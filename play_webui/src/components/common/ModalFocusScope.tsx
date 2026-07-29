'use client'

import {
  type ReactNode,
  type RefObject,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react'
import { createPortal } from 'react-dom'

const MODAL_ROOT_ID = 'modal-root'
const FOCUSABLE_SELECTOR = [
  'a[href]',
  'area[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'iframe',
  '[contenteditable="true"]',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

type AttributeSnapshot = {
  element: HTMLElement
  inert: boolean
  ariaHidden: string | null
}

type ModalEntry = {
  id: number
  containerRef: RefObject<HTMLElement | null>
  initialFocusRef?: RefObject<HTMLElement | null>
  dismissible: boolean
  suspended: boolean
  onDismiss: () => void
  returnTarget: HTMLElement | null
  hiddenSnapshot: AttributeSnapshot | null
}

let nextModalId = 1
const modalStack: ModalEntry[] = []
const backgroundSnapshots = new Map<HTMLElement, AttributeSnapshot>()
let backgroundLocked = false
let bodyOverflowBeforeLock = ''

function scheduleFrame(callback: () => void) {
  if (typeof window.requestAnimationFrame === 'function') {
    return window.requestAnimationFrame(callback)
  }
  return window.setTimeout(callback, 0)
}

function cancelFrame(handle: number | null) {
  if (handle === null) return
  if (typeof window.cancelAnimationFrame === 'function') {
    window.cancelAnimationFrame(handle)
    return
  }
  window.clearTimeout(handle)
}

function captureAttributes(element: HTMLElement): AttributeSnapshot {
  return {
    element,
    inert: element.hasAttribute('inert'),
    ariaHidden: element.getAttribute('aria-hidden'),
  }
}

function hideElement(element: HTMLElement) {
  element.setAttribute('inert', '')
  element.setAttribute('aria-hidden', 'true')
}

function restoreAttributes(snapshot: AttributeSnapshot) {
  if (snapshot.inert) snapshot.element.setAttribute('inert', '')
  else snapshot.element.removeAttribute('inert')

  if (snapshot.ariaHidden === null) snapshot.element.removeAttribute('aria-hidden')
  else snapshot.element.setAttribute('aria-hidden', snapshot.ariaHidden)
}

function lockBackground() {
  const modalRoot = document.getElementById(MODAL_ROOT_ID)
  if (!modalRoot) return

  if (!backgroundLocked) {
    backgroundLocked = true
    bodyOverflowBeforeLock = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  }

  Array.from(document.body.children).forEach((child) => {
    if (!(child instanceof HTMLElement) || child === modalRoot) return
    if (['SCRIPT', 'STYLE', 'LINK'].includes(child.tagName)) return
    if (!backgroundSnapshots.has(child)) {
      backgroundSnapshots.set(child, captureAttributes(child))
    }
    hideElement(child)
  })
}

function unlockBackground() {
  backgroundSnapshots.forEach(restoreAttributes)
  backgroundSnapshots.clear()
  if (backgroundLocked) document.body.style.overflow = bodyOverflowBeforeLock
  backgroundLocked = false
}

function setEntryHidden(entry: ModalEntry, hidden: boolean) {
  const container = entry.containerRef.current
  if (!container) return

  if (hidden) {
    if (!entry.hiddenSnapshot || entry.hiddenSnapshot.element !== container) {
      if (entry.hiddenSnapshot) restoreAttributes(entry.hiddenSnapshot)
      entry.hiddenSnapshot = captureAttributes(container)
    }
    hideElement(container)
    return
  }

  if (entry.hiddenSnapshot) {
    restoreAttributes(entry.hiddenSnapshot)
    entry.hiddenSnapshot = null
  }
}

function syncModalState() {
  if (!modalStack.length) {
    unlockBackground()
    return
  }

  lockBackground()
  const topIndex = modalStack.length - 1
  modalStack.forEach((entry, index) => {
    setEntryHidden(entry, index !== topIndex || entry.suspended)
  })
}

function topModal() {
  return modalStack[modalStack.length - 1] ?? null
}

function focusableElements(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
    .filter((element) => (
      !element.hasAttribute('disabled')
      && !element.hidden
      && !element.closest('[inert], [aria-hidden="true"]')
    ))
}

function focusElement(element: HTMLElement) {
  try {
    element.focus({ preventScroll: true })
  } catch {
    element.focus()
  }
}

function requestedInitialTarget(entry: ModalEntry) {
  const container = entry.containerRef.current
  if (!container) return null
  const requested = entry.initialFocusRef?.current
  return requested
    && container.contains(requested)
    && !requested.closest('[inert], [aria-hidden="true"]')
    ? requested
    : null
}

function focusInitial(entry: ModalEntry) {
  const container = entry.containerRef.current
  if (!container || entry.suspended || topModal() !== entry) return false
  const requested = requestedInitialTarget(entry)
  const target = requested ?? focusableElements(container)[0] ?? container
  focusElement(target)
  return target === requested
}

function handOffReturnTarget(
  closingEntry: ModalEntry,
  replacementEntry: ModalEntry | null,
  closingContainer: HTMLElement | null,
) {
  if (
    !replacementEntry
    || !closingEntry.returnTarget?.isConnected
    || closingContainer?.contains(closingEntry.returnTarget)
  ) {
    return
  }
  if (
    !replacementEntry.returnTarget?.isConnected
    || replacementEntry.returnTarget === document.body
    || Boolean(closingContainer?.contains(replacementEntry.returnTarget))
  ) {
    replacementEntry.returnTarget = closingEntry.returnTarget
  }
}

export type ModalFocusScopeProps = {
  containerRef: RefObject<HTMLElement | null>
  dismissible: boolean
  suspended?: boolean
  initialFocusRef?: RefObject<HTMLElement | null>
  onDismiss: () => void
}

export function useModalFocusScope({
  containerRef,
  dismissible,
  suspended = false,
  initialFocusRef,
  onDismiss,
}: ModalFocusScopeProps) {
  const entryRef = useRef<ModalEntry | null>(null)
  const focusFrameRef = useRef<number | null>(null)
  const latestConfigRef = useRef({
    containerRef,
    dismissible,
    suspended,
    initialFocusRef,
    onDismiss,
  })
  latestConfigRef.current = {
    containerRef,
    dismissible,
    suspended,
    initialFocusRef,
    onDismiss,
  }

  useLayoutEffect(() => {
    const config = latestConfigRef.current
    let initialFocusObserver: MutationObserver | null = null
    const entry: ModalEntry = {
      id: nextModalId++,
      containerRef: config.containerRef,
      initialFocusRef: config.initialFocusRef,
      dismissible: config.dismissible,
      suspended: config.suspended,
      onDismiss: config.onDismiss,
      returnTarget: document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null,
      hiddenSnapshot: null,
    }

    const watchForInitialTarget = () => {
      if (
        initialFocusObserver
        || !entry.initialFocusRef
        || typeof MutationObserver === 'undefined'
      ) {
        return
      }
      const container = entry.containerRef.current
      if (!container) return

      const focusRequestedTarget = () => {
        const requested = requestedInitialTarget(entry)
        if (!requested) return

        const active = document.activeElement
        if (
          active === document.body
          || active === container
          || !(active instanceof HTMLElement)
          || !active.isConnected
          || !container.contains(active)
        ) {
          focusElement(requested)
        }
        initialFocusObserver?.disconnect()
        initialFocusObserver = null
      }

      initialFocusObserver = new MutationObserver(focusRequestedTarget)
      initialFocusObserver.observe(container, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['aria-hidden', 'disabled', 'hidden', 'inert'],
      })
      focusRequestedTarget()
    }

    entryRef.current = entry
    modalStack.push(entry)
    syncModalState()

    if (!entry.suspended) {
      focusFrameRef.current = scheduleFrame(() => {
        focusFrameRef.current = null
        if (!focusInitial(entry)) watchForInitialTarget()
      })
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (topModal() !== entry) return

      if (entry.suspended) {
        if (event.key === 'Escape' || event.key === 'Tab') {
          event.preventDefault()
          event.stopImmediatePropagation()
        }
        return
      }

      if (event.key === 'Escape') {
        event.preventDefault()
        event.stopImmediatePropagation()
        if (entry.dismissible) entry.onDismiss()
        return
      }
      if (event.key !== 'Tab') return

      const container = entry.containerRef.current
      if (!container) return
      const focusable = focusableElements(container)
      if (!focusable.length) {
        event.preventDefault()
        focusElement(container)
        return
      }

      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement
      if (event.shiftKey && (active === first || !container.contains(active))) {
        event.preventDefault()
        focusElement(last)
      } else if (!event.shiftKey && (active === last || !container.contains(active))) {
        event.preventDefault()
        focusElement(first)
      }
    }

    const handleFocusIn = (event: FocusEvent) => {
      if (topModal() !== entry || entry.suspended) return
      const container = entry.containerRef.current
      if (!container || container.contains(event.target as Node)) return
      focusInitial(entry)
    }

    document.addEventListener('keydown', handleKeyDown, true)
    document.addEventListener('focusin', handleFocusIn, true)
    return () => {
      cancelFrame(focusFrameRef.current)
      focusFrameRef.current = null
      initialFocusObserver?.disconnect()
      initialFocusObserver = null
      document.removeEventListener('keydown', handleKeyDown, true)
      document.removeEventListener('focusin', handleFocusIn, true)

      const container = entry.containerRef.current
      const activeElement = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null
      const shouldRestore = !activeElement
        || activeElement === document.body
        || Boolean(container?.contains(activeElement))
      const index = modalStack.findIndex((candidate) => candidate.id === entry.id)
      if (index !== -1) modalStack.splice(index, 1)
      setEntryHidden(entry, false)
      const replacementTop = topModal()
      handOffReturnTarget(entry, replacementTop, container)
      syncModalState()
      entryRef.current = null

      if (!shouldRestore) return
      scheduleFrame(() => {
        const nextTop = topModal()
        handOffReturnTarget(entry, nextTop, container)
        const activeNow = document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null
        if (
          activeNow
          && activeNow !== document.body
          && !container?.contains(activeNow)
          && !activeNow.closest('[inert], [aria-hidden="true"]')
        ) {
          return
        }
        const returnTarget = entry.returnTarget
        if (nextTop) {
          if (
            returnTarget
            && nextTop.containerRef.current?.contains(returnTarget)
            && !returnTarget.closest('[inert], [aria-hidden="true"]')
          ) {
            focusElement(returnTarget)
          } else {
            focusInitial(nextTop)
          }
          return
        }
        if (
          returnTarget?.isConnected
          && !returnTarget.closest('[inert], [aria-hidden="true"]')
        ) {
          focusElement(returnTarget)
        }
      })
    }
  }, [])

  useLayoutEffect(() => {
    const entry = entryRef.current
    if (!entry) return
    const wasSuspended = entry.suspended
    entry.containerRef = containerRef
    entry.initialFocusRef = initialFocusRef
    entry.dismissible = dismissible
    entry.suspended = suspended
    entry.onDismiss = onDismiss
    syncModalState()

    if (wasSuspended && !suspended && topModal() === entry) {
      cancelFrame(focusFrameRef.current)
      focusFrameRef.current = scheduleFrame(() => {
        focusFrameRef.current = null
        focusInitial(entry)
      })
    }
  }, [containerRef, dismissible, initialFocusRef, onDismiss, suspended])
}

export function ModalFocusScope({
  children,
  ...props
}: ModalFocusScopeProps & { children: ReactNode }) {
  useModalFocusScope(props)
  return children
}

function ensureModalRoot() {
  const existing = document.getElementById(MODAL_ROOT_ID)
  if (existing) return existing
  const created = document.createElement('div')
  created.id = MODAL_ROOT_ID
  created.dataset.runtimeModalRoot = 'true'
  document.body.append(created)
  return created
}

export function ModalPortal({ children }: { children: ReactNode }) {
  const [root, setRoot] = useState<HTMLElement | null>(null)

  useEffect(() => {
    setRoot(ensureModalRoot())
  }, [])

  return root ? createPortal(children, root) : null
}
