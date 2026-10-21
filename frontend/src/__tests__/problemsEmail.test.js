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

const email = { access_key: 'k', report_id: 'AB12CD34', message: 'It stops after a minute' }
const URL = 'https://api.web3forms.com/submit'

let problems
beforeEach(async () => {
  vi.resetModules()
  for (const fn of Object.values(api)) fn.mockClear()
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
    expect(api.holdReport).toHaveBeenCalledWith(email)

    api.heldReports.mockResolvedValue({ data: { emails: [email], url: URL } })
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) })))
    expect(await problems.sendHeldReports()).toBe(1)
    expect(api.reportDone).toHaveBeenCalledWith('AB12CD34')
  })

  it('a form that refuses it is not taken for sent', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({ success: false, message: 'Invalid access key' }) })))
    const out = await problems.useReporting().send({ description: 'It stops after a minute' })
    expect(out.status).toBe('queued')
  })
})
