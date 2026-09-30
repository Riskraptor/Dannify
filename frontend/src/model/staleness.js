// The version this page was built as (see vite.config.js).
const BUILT_AS = typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : ''

// Whether this page is older than the app serving it. Every first start after
// an update used to reload the window, to get away from cached files. By then
// the new interface was already running (index.html is never cached, and every
// other file's name changes with its contents), so the reload only flashed
// the window, and threw away whatever had just been handed to the first page:
// a song double-clicked in Explorer at that moment never played. Now it
// reloads only when it really is out of date, and only once.
export function pageIsStale(stored, server, built = BUILT_AS) {
  if (!server) return false
  const stale = built ? built !== server : !!stored && stored !== '0.0.0' && stored !== server
  if (!stale) return false
  try {
    if (sessionStorage.getItem('dn.reloadedFor') === server) return false
    sessionStorage.setItem('dn.reloadedFor', server)
  } catch {
    // Without session storage there is no way to know it has already tried.
    return false
  }
  return true
}
