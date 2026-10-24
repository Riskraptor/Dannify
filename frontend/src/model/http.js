// Talking to Dannify's own server, on the browser's own fetch.
//
// Shaped like the library it replaces (axios), so nothing that calls it had to
// change: get, post, patch, put and delete; `params`, `timeout` and `signal`;
// a promise of `{ data, status, headers }`. A request the server answered with
// an error rejects with `.response = { status, data }`; one it never answered
// rejects without a response, with `code` 'ECONNABORTED' when it timed out and
// name 'CanceledError' when it was called off. That library was the heaviest
// thing the window loaded after Vue itself, for what fetch already does.

function query(params) {
  const q = new URLSearchParams()
  for (const [key, value] of Object.entries(params || {})) {
    if (value === undefined || value === null) continue
    if (Array.isArray(value)) value.forEach((v) => q.append(key, String(v)))
    else q.append(key, String(value))
  }
  return q.toString()
}

function failure(message, extra) {
  const err = new Error(message)
  err.isAxiosError = true // what the rest of the app checks for
  return Object.assign(err, extra)
}

async function readBody(res) {
  const text = await res.text()
  if (!text) return ''
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

export function createClient({ baseURL = '' } = {}) {
  async function request(method, url, data, config = {}) {
    let full = /^[a-z]+:/i.test(url) ? url : baseURL + url
    const qs = query(config.params)
    if (qs) full += (full.includes('?') ? '&' : '?') + qs

    const headers = { Accept: 'application/json, text/plain, */*', ...(config.headers || {}) }
    let body
    if (data !== undefined && data !== null) {
      const raw = typeof data === 'string' || data instanceof Blob || data instanceof FormData
      body = raw ? data : JSON.stringify(data)
      if (!raw) headers['Content-Type'] = 'application/json'
    }

    // One controller for the time limit and for whoever may call it off.
    const controller = new AbortController()
    let timedOut = false
    const timeout = Number(config.timeout) || 0
    const timer = timeout > 0 ? setTimeout(() => ((timedOut = true), controller.abort()), timeout) : 0
    const outer = config.signal
    const forward = () => controller.abort()
    if (outer) {
      if (outer.aborted) controller.abort()
      else outer.addEventListener('abort', forward, { once: true })
    }

    let res
    try {
      res = await fetch(full, { method, headers, body, signal: controller.signal })
    } catch (err) {
      if (timedOut) throw failure(`timeout of ${timeout}ms exceeded`, { code: 'ECONNABORTED' })
      if (controller.signal.aborted) throw failure('canceled', { name: 'CanceledError', code: 'ERR_CANCELED' })
      throw failure('Network Error', { code: 'ERR_NETWORK', cause: err })
    } finally {
      clearTimeout(timer)
      if (outer) outer.removeEventListener('abort', forward)
    }

    const response = { data: await readBody(res).catch(() => ''), status: res.status, headers: res.headers }
    if (!res.ok) {
      throw failure(`Request failed with status code ${res.status}`, { response, status: res.status })
    }
    return response
  }

  return {
    get: (url, config) => request('GET', url, undefined, config),
    delete: (url, config) => request('DELETE', url, undefined, config),
    post: (url, data, config) => request('POST', url, data, config),
    put: (url, data, config) => request('PUT', url, data, config),
    patch: (url, data, config) => request('PATCH', url, data, config),
  }
}
