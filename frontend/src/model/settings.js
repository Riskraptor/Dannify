import { ref, computed } from 'vue'

import API from '/src/model/api'

const settings = ref({
  audio_providers: [''],
  download_lyrics: true,
  format: '',
  bitrate: '320',
  output: '',
  generate_m3u: true,
  organize_by_artist: false,
  max_parallel_downloads: 3,
  download_dir: '',
  lyrics_storage: 'sidecar',
})

const settingsOptions = {
  audio_providers: ['youtube', 'youtube-music'],
  format: ['mp3', 'flac', 'ogg', 'opus', 'm4a'],
  bitrate: ['128', '192', '256', '320'],
  max_parallel_downloads: [1, 2, 3, 5, 8],
  output: '{artists} - {title}.{output-ext}',
  lyrics_storage: ['sidecar', 'central'],
}

// Timestamp of the last successful save (drives the "Saved" indicator).
const lastSaved = ref(0)

API.getSettings()
  .then((res) => {
    if (res.status === 200) settings.value = res.data
  })
  .catch(() => {})

export function useSettingsManager() {
  const isSaved = ref()
  function saveSettings() {
    console.log('Saving settings:', settings.value)
    API.setSettings(settings.value).then((res) => {
      if (res.status === 200) {
        console.log('Saved!')
        isSaved.value = true
        setTimeout(() => {
          isSaved.value = null
        }, 2000)
      } else {
        console.error('Error saving settings.', res)
        isSaved.value = false
        setTimeout(() => {
          isSaved.value = null
        }, 2000)
      }
    })
  }

  // Open the OS-native folder picker and, on success, save the new path
  // immediately (no need for a second "Save" click: the backend applies
  // it live without restart). Returns the chosen path so callers can
  // show a friendly confirmation.
  async function pickDownloadFolder() {
    try {
      const res = await API.pickFolder()
      if (!res?.data?.path) return ''
      const path = res.data.path
      const prev = settings.value.download_dir
      settings.value.download_dir = path
      // Persist + apply live.
      const saveRes = await API.setSettings({ download_dir: path })
      if (saveRes.status === 200 && saveRes.data) {
        // Server may have normalized the path: trust its echo.
        settings.value = { ...settings.value, ...saveRes.data }
        isSaved.value = true
        lastSaved.value = Date.now()
        setTimeout(() => { isSaved.value = null }, 2000)
        return saveRes.data.download_dir || path
      }
      // Server rejected the path (read-only, etc.): revert.
      settings.value.download_dir = prev
      isSaved.value = false
      setTimeout(() => { isSaved.value = null }, 2500)
      return ''
    } catch (err) {
      console.error('pickDownloadFolder failed', err)
      isSaved.value = false
      setTimeout(() => { isSaved.value = null }, 2500)
      return ''
    }
  }

  // Apply + persist a partial change immediately (the backend merges the
  // patch and echoes the full settings back).
  async function update(patch) {
    const prev = { ...settings.value }
    settings.value = { ...settings.value, ...patch }
    try {
      const res = await API.setSettings(patch)
      if (res.status === 200 && res.data) {
        settings.value = { ...settings.value, ...res.data }
        isSaved.value = true
        lastSaved.value = Date.now()
      } else {
        settings.value = prev
        isSaved.value = false
      }
    } catch {
      settings.value = prev
      isSaved.value = false
    }
    setTimeout(() => {
      isSaved.value = null
    }, 2000)
    return isSaved.value === true
  }

  async function setLyricsStorage(mode) {
    if (mode !== 'sidecar' && mode !== 'central') return
    settings.value.lyrics_storage = mode
    try {
      const res = await API.setSettings({ lyrics_storage: mode })
      if (res.status === 200 && res.data) {
        settings.value = { ...settings.value, ...res.data }
        isSaved.value = true
        lastSaved.value = Date.now()
      } else {
        isSaved.value = false
      }
    } catch {
      isSaved.value = false
    }
    setTimeout(() => { isSaved.value = null }, 2000)
  }

  return {
    saveSettings,
    update,
    settings,
    settingsOptions,
    isSaved,
    lastSaved,
    pickDownloadFolder,
    setLyricsStorage,
  }
}
