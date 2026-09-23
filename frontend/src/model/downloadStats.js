import { computed } from 'vue'
import { useProgressTracker } from '/src/model/download'

// Aggregate numbers for the download queue (title-bar indicator, sidebar
// badge, taskbar progress).

const { downloadQueue } = useProgressTracker()

const stats = computed(() => {
  let active = 0
  let done = 0
  let failed = 0
  let progressSum = 0
  for (const item of downloadQueue.value) {
    if (item.isErrored()) failed++
    else if (item.isDownloaded()) done++
    else {
      active++
      progressSum += Math.max(0, Math.min(100, Number(item.progress) || 0))
    }
  }
  return {
    total: downloadQueue.value.length,
    active,
    done,
    failed,
    percent: active ? progressSum / active : 0,
  }
})

export function useDownloadStats() {
  return stats
}
