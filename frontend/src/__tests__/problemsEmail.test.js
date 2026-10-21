import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Problem reports by email: the app prepares it, the window sends it to
// Web3Forms, and one that cannot go is kept for later (model/problems.js).
const api = {
  getReportStatus: vi.fn(() => Promise.resolve({ data: { enabled: true, mode: 'email', pending: 0 } })),
  sendReport: vi.fn(),
  holdReport: vi.fn(() => Promise.resolve({})),
  heldReports: vi.fn(),
  reportDone: vi.fn(() => Promise.resolve({})),
  reportClientError: vi.fn(() => Promise.resolve({})),
}
vi.mock('/src/model/api', () => ({ default: api }))
vi.mock('/src/router', () => ({ default: { currentRoute: { value: { fullPath: '/' } } } }))
vi.mock('/src/desktop/fullWindow', () => ({ ensureFullWindow: () => Promise.resolve() }))
const env = vi.hoisted(() => ({ waiters: [], toasts: [], online: false }))
vi.mock('/src/model/connectivity', () => ({
  useConnectivity: () => ({ probe: () => Promise.resolve(env.online) }),
  whenOnline: (fn) => env.waiters.push(fn),
}))
vi.mock('/src/model/toast', () => ({ toast: (msg, opts) => env.toasts.push({ msg, opts }) }))
vi.mock('/src/i18n', () => ({ t: (key) => key }))

const email = { access_key: 'k', report_id: 'AB12CD34', message: 'It stops after a minute' }
const URL = 'https://api.web3forms.com/submit'

let problems
beforeEach(async () => {
  vi.resetModules()
  for (const fn of Object.values(api)) fn.mockClear()
  env.waiters.length = 0
  env.toasts.length = 0
  api.getReportStatus.mockResolvedValue({ data: { enabled: true, mode: 'email', pending: 0 } })
  api.sendReport.mockResolvedValue({ data: { id: 'AB12CD34', status: 'prepared', email, url: URL } })
  problems = await import('../model/problems.js')
})
afterEach(() => vi.unstubAllGlobals())

describe('a report by email', () => {
  it('goes from the window, and nothing is kept', async () => {
    const fetch = vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) }))
    vi.stubGlobal('fetch', fetch)
    const out = await problems.useReporting().send({ description: 'It stops after a minute' })
    expect(out).toEqual({ id: 'AB12CD34', status: 'sent' })
    expect(fetch).toHaveBeenCalledWith(URL, expect.objectContaining({ method: 'POST', body: JSON.stringify(email) }))
    expect(api.holdReport).not.toHaveBeenCalled()
  })

  it('offline, is kept and goes next time', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))))
    const out = await problems.useReporting().send({ description: 'It stops after a minute' })
    expect(out.status).toBe('queued')
    expect(api.holdReport).toHaveBeenCalledWith(expect.objectContaining({ ...email, held_preview: 'It stops after a minute' }))

    api.heldReports.mockResolvedValue({ data: { emails: [email], url: URL } })
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) })))
    expect(await problems.sendHeldReports()).toBe(1)
    expect(api.reportDone).toHaveBeenCalledWith('AB12CD34')
  })

  it('a form that refuses it is not taken for sent, nor kept to fail again', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({ success: false, message: 'hCaptcha Token is mandatory for this form' }) })))
    await expect(problems.useReporting().send({ description: 'It stops after a minute' })).rejects.toThrow(/hCaptcha/)
    expect(api.holdReport).not.toHaveBeenCalled()
  })

  it('carries the solved check; offline with one, it is kept and offered once back', async () => {
    const fetch = vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) }))
    vi.stubGlobal('fetch', fetch)
    await problems.useReporting().send({ description: 'It stops after a minute' }, 'P1_token')
    expect(JSON.parse(fetch.mock.calls[0][1].body)['h-captcha-response']).toBe('P1_token')

    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))))
    const out = await problems.useReporting().send({ description: 'It stops after a minute' }, 'P1_token')
    expect(out).toMatchObject({ status: 'queued', needsYou: true })
    expect(api.holdReport).toHaveBeenCalledTimes(1)
    // The kept copy does not carry the spent check.
    expect(api.holdReport.mock.calls[0][0]['h-captcha-response']).toBeUndefined()
    await new Promise((r) => setTimeout(r, 0))
    expect(env.waiters).toHaveLength(1)
  })

  it('a kept report the form wants checked is offered, and sent with one slide', async () => {
    api.getReportStatus.mockResolvedValue({ data: { enabled: true, mode: 'email', pending: 1, captcha: { provider: 'hcaptcha', sitekey: 'k' } } })
    const kept = { ...email, held_preview: 'It stops after a minute', held_at: 1 }
    api.heldReports.mockResolvedValue({ data: { emails: [kept], url: URL } })
    const fetch = vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) }))
    vi.stubGlobal('fetch', fetch)
    // Not sent by itself: it would be refused without a check.
    expect(await problems.sendHeldReports()).toBe(0)
    expect(fetch).not.toHaveBeenCalled()
    expect(env.toasts[0].msg).toBe('problems.heldReady')
    // "Send it now": the dialog opens on it.
    env.toasts[0].opts.action.run()
    const reporting = problems.useReporting()
    expect(reporting.held.value.email.report_id).toBe('AB12CD34')
    const out = await reporting.sendHeld('P2_token')
    expect(out).toEqual({ id: 'AB12CD34', status: 'sent' })
    const sent = JSON.parse(fetch.mock.calls[0][1].body)
    expect(sent['h-captcha-response']).toBe('P2_token')
    expect(sent.held_preview).toBeUndefined()
    expect(sent.held_at).toBeUndefined()
    expect(api.reportDone).toHaveBeenCalledWith('AB12CD34')
  })

  it('a waiting report the form now refuses is let go, not tried at every start', async () => {
    api.heldReports.mockResolvedValue({ data: { emails: [email], url: URL } })
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({ success: false, message: 'hCaptcha Token is mandatory for this form' }) })))
    expect(await problems.sendHeldReports()).toBe(0)
    expect(api.reportDone).toHaveBeenCalledWith('AB12CD34')
  })
})
