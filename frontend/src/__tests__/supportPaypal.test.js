import { beforeEach, describe, expect, it, vi } from 'vitest'

// Giving by PayPal: in a window of Dannify's own, thanked for when paid, and
// the browser where there is no such window (model/support.js).
const desktop = { isDesktop: true, checkout: vi.fn(), openExternal: vi.fn() }
const toasts = []
vi.mock('/src/desktop/bridge', () => ({ desktop }))
vi.mock('/src/model/api', () => ({ default: { getSupportConfig: vi.fn(() => Promise.resolve({ data: {} })) } }))
vi.mock('/src/model/toast', () => ({ toast: (msg, opts) => toasts.push({ msg, opts }) }))
vi.mock('/src/i18n', () => ({ t: (key) => key }))

const LINK = 'https://www.paypal.com/ncp/payment/PLB-6P7SEVNLQBY9'

let support
beforeEach(async () => {
  vi.resetModules()
  toasts.length = 0
  desktop.checkout.mockReset()
  desktop.openExternal.mockReset()
  desktop.isDesktop = true
  vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => {}, removeItem: () => {} })
  support = await import('../model/support.js')
  support.useSupport().config.paypal_link = LINK
})

describe('giving by PayPal', () => {
  it('opens inside the app, and thanks for a payment that went through', async () => {
    desktop.checkout.mockResolvedValue({ opened: true, paid: true })
    const giving = support.giveByPaypal()
    expect(support.checkingOut.value).toBe(true)
    await giving
    expect(desktop.checkout).toHaveBeenCalledWith(LINK, 'support.checkoutTitle')
    expect(support.checkingOut.value).toBe(false)
    expect(support.thankedAt.value).toBeGreaterThan(0)
    expect(toasts[0].msg).toBe('support.thanksToast')
    expect(desktop.openExternal).not.toHaveBeenCalled()
  })

  it('closed without paying: no thanks, and nothing else opens', async () => {
    desktop.checkout.mockResolvedValue({ opened: true, paid: false })
    await support.giveByPaypal()
    expect(support.thankedAt.value).toBe(0)
    expect(toasts).toHaveLength(0)
    expect(desktop.openExternal).not.toHaveBeenCalled()
  })

  it('with no window of its own, the browser', async () => {
    desktop.checkout.mockResolvedValue(undefined)
    await support.giveByPaypal()
    expect(desktop.openExternal).toHaveBeenCalledWith(LINK)
  })

  it('asked for the browser, the browser', async () => {
    await support.giveByPaypal({ inBrowser: true })
    expect(desktop.checkout).not.toHaveBeenCalled()
    expect(desktop.openExternal).toHaveBeenCalledWith(LINK)
  })
})
