import { ref } from 'vue'
import API from '/src/model/api'
import { toast } from '/src/model/toast'
import { t } from '/src/i18n'

// Refreshing saved songs' details: their title, artists, album, year and
// artwork, fetched again for the same recording and written back around the
// same audio. The server does one at a time and says how it is going.

export const detailsRunning = ref(false)
export const detailsDone = ref(0)
export const detailsTotal = ref(0)

function say(key, params, opts) {
  toast(t(key, params), { icon: 'ph:arrows-clockwise', ...opts })
}

/** Refresh the details of these saved files. Returns how many were sent. */
export async function refreshDetailsFor(files) {
  const list = [...new Set((files || []).filter(Boolean))]
  if (!list.length) return 0
  try {
    const res = await API.refreshDetails(list)
    const queued = (res.data && res.data.queued) || list.length
    detailsRunning.value = true
    detailsTotal.value += queued
    say('details.started', { count: queued }, { timeout: 4000 })
    return queued
  } catch (e) {
    toast(t(e && e.response && e.response.status === 409 ? 'details.noStorage' : 'details.failed'), {
      tone: 'error',
    })
    return 0
  }
}

/** Look artists up again (picture, page), and refresh their saved songs. */
export async function refreshArtists(names, files = []) {
  try {
    await API.refreshArtists(names || [])
    window.dispatchEvent(new CustomEvent('dannify:artists-refreshed'))
  } catch {
    toast(t('details.failed'), { tone: 'error' })
    return
  }
  if (files.length) await refreshDetailsFor(files)
  else toast(t('details.artistsRefreshed'), { icon: 'ph:user-circle', tone: 'success' })
}

if (typeof window !== 'undefined') {
  window.addEventListener('dannify:details', (e) => {
    const data = e.detail || {}
    if (!data.finished) {
      detailsDone.value = Math.max(detailsDone.value, data.done || 0)
      return
    }
    detailsRunning.value = false
    detailsDone.value = 0
    detailsTotal.value = 0
    const updated = data.updated || 0
    const failed = data.failed || 0
    if (failed && !updated) {
      const offline = data.reasons && data.reasons.offline
      toast(t(offline ? 'details.offline' : 'details.noneUpdated', { count: failed }), {
        tone: 'error',
      })
    } else if (failed) {
      toast(t('details.someUpdated', { count: updated, failed }), { tone: 'success' })
    } else {
      toast(t('details.updated', { count: updated }), { tone: 'success', icon: 'ph:check-circle' })
    }
  })
}
