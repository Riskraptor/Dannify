import { desktop } from '/src/desktop/bridge'

// Clipboard helpers that work in the desktop shell (WebView2 won't let a page
// *read* the clipboard without a permission prompt, so paste goes through
// Python) and in plain LAN browsers (no async clipboard on insecure origins).

export async function copyText(text) {
  const value = String(text ?? '')
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value)
      return true
    }
  } catch {
    // fall back below
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = value
    ta.setAttribute('readonly', '')
    ta.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

export async function readText() {
  if (desktop.isDesktop) {
    const text = await desktop.readClipboard()
    if (typeof text === 'string') return text
  }
  try {
    if (navigator.clipboard && window.isSecureContext) {
      return await navigator.clipboard.readText()
    }
  } catch {
    // permission denied
  }
  return ''
}
