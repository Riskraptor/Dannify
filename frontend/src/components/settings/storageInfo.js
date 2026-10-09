import { ref, computed } from 'vue'
import API from '/src/model/api'
import { toast } from '/src/model/toast'
import { t } from '/src/i18n'

// How much the music folder holds and how much room is left. Measured when
// the Library pane is opened, not on every visit to Settings: it walks the
// whole folder. Shared by the folder row (a new folder is measured again)
// and the storage row, through the Settings page.

export const STORAGE_INFO = Symbol('settings-storage')

export function formatBytes(n) {
  const value = Number(n) || 0
  if (value < 1024 * 1024) return `${Math.max(0, Math.round(value / 1024))} KB`
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(value < 10 * 1024 ** 2 ? 1 : 0)} MB`
  return `${(value / 1024 ** 3).toFixed(1)} GB`
}

export function createStorageInfo() {
  const storage = ref(null)
  const clearing = ref(false)
  const usagePct = computed(() => {
    const st = storage.value
    if (!st || !st.free) return 0
    return Math.max(1, Math.min(100, (st.bytes / (st.bytes + st.free)) * 100))
  })

  async function load() {
    try {
      const res = await API.getStorage()
      storage.value = res.data || null
    } catch {
      storage.value = null
    }
  }

  async function clearCaches() {
    clearing.value = true
    try {
      await API.clearCaches()
      // The size beside the button drops to nothing: that is the answer.
      load()
    } catch {
      toast(t('settings.clearFailed'), { tone: 'error' })
    } finally {
      clearing.value = false
    }
  }

  // The folder changed: what was measured is about the old one.
  function remeasure() {
    storage.value = null
    load()
  }

  return { storage, clearing, usagePct, load, clearCaches, remeasure }
}
