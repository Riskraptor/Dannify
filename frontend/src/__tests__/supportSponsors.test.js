import { beforeEach, describe, expect, it, vi } from 'vitest'

// Giving is GitHub Sponsors only, in the browser where GitHub is signed in
// (model/support.js). PayPal, Ko-fi and M-Pesa are gone, whatever the app is
// told about them.
const desktop = { isDesktop: true, checkout: vi.fn(), openExternal: vi.fn() }
vi.mock('/src/desktop/bridge', () => ({ desktop }))
vi.mock('/src/model/api', () => ({
  default: {
    getSupportConfig: vi.fn(() =>
      Promise.resolve({
        data: {
          configured: true,
          sponsors_link: 'https://github.com/sponsors/Riskraptor',
          paypal_link: 'https://www.paypal.com/ncp/payment/PLB-WVTSZMLQNTLQ',
          link: 'https://ko-fi.com/x',
          mpesa: { kind: 'till', number: '8496746' },
        },
      })
    ),
  },
}))

let support
beforeEach(async () => {
  vi.resetModules()
  desktop.checkout.mockReset()
  desktop.openExternal.mockReset()
  vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => {}, removeItem: () => {} })
  support = await import('../model/support.js')
})

describe('giving through GitHub Sponsors', () => {
  it('opens the sponsors page in the browser, where GitHub is signed in', () => {
    support.useSupport().config.sponsors_link = 'https://github.com/sponsors/Riskraptor'
    support.giveBySponsors()
    expect(desktop.openExternal).toHaveBeenCalledWith('https://github.com/sponsors/Riskraptor')
    expect(desktop.checkout).not.toHaveBeenCalled()
  })

  it('does nothing when no sponsors page is set', () => {
    support.useSupport().config.sponsors_link = ''
    support.giveBySponsors()
    expect(desktop.openExternal).not.toHaveBeenCalled()
  })

  it('is the only way there is to give', () => {
    const api = support.useSupport()
    expect(api.giveByPaypal).toBeUndefined()
    expect(api.giveByKofi).toBeUndefined()
    expect(support.giveByPaypal).toBeUndefined()
  })
})
