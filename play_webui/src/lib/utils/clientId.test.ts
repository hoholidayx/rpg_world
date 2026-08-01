import { afterEach, describe, expect, it, vi } from 'vitest'
import { createClientUuid } from './clientId'

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('createClientUuid', () => {
  it('uses crypto.randomUUID when the browser provides it', () => {
    const randomUUID = vi.fn(() => 'b4c24ff0-765a-4e9b-82bd-00d5d5b8961f')
    vi.stubGlobal('crypto', { randomUUID })

    expect(createClientUuid()).toBe('b4c24ff0-765a-4e9b-82bd-00d5d5b8961f')
    expect(randomUUID).toHaveBeenCalledOnce()
  })

  it('uses getRandomValues when randomUUID is absent, as on older iOS WebKit', () => {
    const getRandomValues = vi.fn((bytes: Uint8Array) => {
      bytes.fill(0)
      return bytes
    })
    vi.stubGlobal('crypto', { getRandomValues })

    const id = createClientUuid()

    expect(id).toMatch(UUID_V4)
    expect(getRandomValues).toHaveBeenCalledOnce()
  })

  it('still creates a UUID-shaped local identifier without Web Crypto', () => {
    vi.stubGlobal('crypto', undefined)

    expect(createClientUuid()).toMatch(UUID_V4)
  })
})
