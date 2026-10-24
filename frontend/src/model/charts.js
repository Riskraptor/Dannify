import { ref } from 'vue'
import API from '/src/model/api'
import { region } from '/src/model/occasions'
import { failedForNetwork, whenOnline } from '/src/model/connectivity'

// YouTube Music's charts and new releases, where the listener is (the country
// picked or found in Settings, Special days). Read once a session, shared by
// Home and Search; the server keeps them for six hours.

const data = ref({})
const albums = ref([])
let loadedFor = null
let loading = null

export function loadCharts() {
  const code = region.value || ''
  if (loadedFor === code && (data.value.code || albums.value.length)) return Promise.resolve()
  if (loading) return loading
  loading = Promise.allSettled([API.exploreCharts(code), API.exploreNew()])
    .then(async ([charts, fresh]) => {
      if (charts.status === 'fulfilled') data.value = charts.value.data || {}
      if (fresh.status === 'fulfilled') albums.value = (fresh.value.data && fresh.value.data.albums) || []
      loadedFor = code
      const failed = charts.status === 'rejected' ? charts.reason : fresh.status === 'rejected' ? fresh.reason : null
      // Offline: loaded again once the connection is back.
      if (failed && (await failedForNetwork(failed))) {
        loadedFor = null
        whenOnline(() => loadCharts())
      }
    })
    .finally(() => {
      loading = null
    })
  return loading
}

export function useCharts() {
  return { data, albums, load: loadCharts }
}
