<script setup>
/**
 * What is wrong, on screen, instead of nowhere.
 *
 * Every failure in this app so far has been a silent one. The key that saved
 * music is locked with could not be read, and what the person saw was a
 * library of grey squares with no album names and no lengths, and a play
 * button that said the file may have been moved or deleted. Nothing said the
 * real reason. The same fault was worked out from scratch three separate
 * times, twice from a screenshot.
 *
 * So the backend checks what it needs on every start and says what is
 * missing, and this puts it where the person it is happening to can read it.
 * It says what is wrong and what it means for them. It never mentions a log.
 */
import { onMounted, ref } from 'vue'
import API from '/src/model/api'
import { t } from '/src/i18n'

const problems = ref([])
const dismissed = ref(false)

async function check() {
  try {
    const res = await API.health()
    problems.value = (res && res.data && res.data.problems) || []
  } catch {
    // The backend not answering is its own kind of broken, but the window
    // cannot say much about it from here and the rest of the app will make
    // the failure obvious soon enough.
    problems.value = []
  }
}

function messageFor(p) {
  if (p.code === 'music_locked') {
    return t('health.musicLocked', { count: p.tracks })
  }
  if (p.code === 'no_key') return t('health.noKey')
  if (p.code === 'folder_missing') return t('health.folderMissing', { path: p.path })
  if (p.code === 'folder_read_only') return t('health.folderReadOnly', { path: p.path })
  if (p.code === 'update_failed') {
    return t('health.updateFailed', { wanted: p.wanted, running: p.running })
  }
  return ''
}

onMounted(check)
window.addEventListener('dannify:library-changed', check)
</script>

<template>
  <div v-if="problems.length && !dismissed" class="health" role="alert">
    <span class="health-mark" aria-hidden="true">!</span>
    <div class="health-text">
      <p v-for="p in problems" :key="p.code">{{ messageFor(p) }}</p>
    </div>
    <button class="health-close" :title="t('common.dismiss')" @click="dismissed = true">
      ×
    </button>
  </div>
</template>

<style scoped>
.health {
  display: flex;
  flex: none;
  align-items: flex-start;
  gap: 12px;
  margin: 16px 24px 4px;
  padding: 12px 14px;
  max-width: 900px;
  border: 1px solid var(--danger-border, rgba(255 107 107 / 0.35));
  border-radius: 10px;
  background: var(--danger-bg, rgba(255 107 107 / 0.1));
  color: var(--text, inherit);
  font-size: 0.9rem;
  line-height: 1.45;
}

.health-mark {
  flex: none;
  width: 20px;
  height: 20px;
  margin-top: 1px;
  border-radius: 50%;
  background: var(--danger, #ff6b6b);
  color: #fff;
  font-weight: 700;
  font-size: 0.78rem;
  line-height: 20px;
  text-align: center;
}

.health-text {
  flex: 1;
  min-width: 0;
}

.health-text p {
  margin: 0;
}

.health-text p + p {
  margin-top: 6px;
}

.health-close {
  flex: none;
  border: 0;
  background: none;
  color: inherit;
  opacity: 0.6;
  font-size: 1.1rem;
  line-height: 1;
  cursor: pointer;
  padding: 2px 4px;
}

.health-close:hover {
  opacity: 1;
}

@media (width <= 700px) {
  .health {
    margin: 0 16px 10px;
  }
}
</style>
