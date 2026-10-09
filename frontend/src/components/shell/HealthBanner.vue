<script setup>
/**
 * What is wrong, on screen, instead of nowhere.
 *
 * Every failure in this app used to be a silent one: songs that would not
 * play looked like songs with their details missing, and the play button said
 * the file may have been moved or deleted. So the backend checks what it needs
 * and says what is missing, and this puts it where the person it is happening
 * to can read it, with the fix as a button beside it.
 *
 * Deliberately plain. It says a song will not play and offers to repair it;
 * it never explains how saved songs are protected, because naming the
 * mechanism in a message only invites somebody to go and poke at it. It is a
 * calm note rather than an alarm, it keeps out of the Now Playing screen, and
 * while a repair is running it steps aside for the ring in the title bar
 * instead of repeating the problem next to a count that disagrees with it.
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { t } from '/src/i18n'
import { tp } from '/src/i18n/platform'
import { useRepair } from '/src/model/repair'

const props = defineProps({
  // True on screens it must stay off (Now Playing). A prop rather than
  // v-show from outside: the root here is a transition that is sometimes
  // empty, and a directive from the parent did not reliably reach the note
  // inside it, so it went on showing over the album art.
  away: { type: Boolean, default: false },
})

const problems = ref([])
const dismissed = ref(false)
const repair = useRepair()
const running = computed(() => !!repair.status.value.running)

async function check() {
  try {
    const res = await API.health()
    const found = (res && res.data && res.data.problems) || []
    // Only clear what was showing once the check has actually succeeded and
    // come back empty. Clearing on failure would be the silence this whole
    // component exists to end.
    problems.value = found
    if (found.length) dismissed.value = false
  } catch {
    problems.value = [{ code: 'check_failed' }]
  }
}

// Checked again whenever the library changes, but once per burst: a repair
// changes it every few seconds, and every check reads every saved song.
let soon = null
function checkSoon() {
  clearTimeout(soon)
  soon = setTimeout(check, 1500)
}

function messageFor(p) {
  if (p.code === 'songs_unplayable') return t('health.songsUnplayable', { count: p.tracks })
  if (p.code === 'storage_unavailable') return t('health.storageUnavailable')
  if (p.code === 'folder_missing') return t('health.folderMissing', { path: p.path })
  if (p.code === 'folder_read_only') return t('health.folderReadOnly', { path: p.path })
  if (p.code === 'check_failed') return tp('health.checkFailed')
  if (p.code === 'update_failed') {
    return t('health.updateFailed', { wanted: p.wanted, running: p.running })
  }
  return ''
}

const shown = computed(() => problems.value.filter((p) => messageFor(p)))
const repairable = computed(() =>
  shown.value.find((p) => p.code === 'songs_unplayable' && p.repairable)
)
const visible = computed(
  () => !props.away && !dismissed.value && !running.value && shown.value.length > 0
)

// A repair finishing is a reason to look again straight away.
watch(running, (now, before) => {
  if (before && !now) check()
})

// Registered on mount and taken off again on unmount. Toggling the mini player
// unmounts the whole shell, so a listener added at module scope would be added
// again every time and the check would run once per toggle, for ever.
onMounted(() => {
  check()
  window.addEventListener('dannify:library-changed', checkSoon)
})
onUnmounted(() => {
  clearTimeout(soon)
  window.removeEventListener('dannify:library-changed', checkSoon)
})
</script>

<template>
  <transition name="note">
    <div v-if="visible" class="note" role="status">
      <Icon icon="ph:warning-circle-fill" class="note-mark" aria-hidden="true" />
      <div class="note-text">
        <p v-for="p in shown" :key="p.code">{{ messageFor(p) }}</p>
      </div>
      <button
        v-if="repairable"
        class="btn-accent btn-pill press note-btn"
        @click="repair.repairAll()"
      >
        <Icon icon="ph:wrench" class="h-4 w-4" />
        {{ repairable.tracks > 1 ? t('repair.all') : t('repair.action') }}
      </button>
      <button class="note-close" :title="t('common.dismiss')" :aria-label="t('common.dismiss')" @click="dismissed = true">
        <Icon icon="ph:x" class="h-4 w-4" />
      </button>
    </div>
  </transition>
</template>

<style scoped>
.note {
  display: flex;
  flex: none;
  align-items: center;
  gap: 12px;
  margin: 16px 24px 4px;
  padding: 10px 10px 10px 14px;
  max-width: 900px;
  border: 1px solid rgb(var(--c-tint) / 0.1);
  border-radius: 10px;
  background: rgb(var(--c-tint) / 0.05);
  font-size: 0.88rem;
  line-height: 1.45;
}

.note-mark {
  flex: none;
  width: 18px;
  height: 18px;
  color: rgb(var(--c-warn));
}

.note-text {
  flex: 1;
  min-width: 0;
  color: rgb(var(--c-fg) / 0.9);
}

.note-text p {
  margin: 0;
}

.note-text p + p {
  margin-top: 4px;
}

.note-btn {
  flex: none;
  height: 30px;
  padding: 0 14px;
  gap: 6px;
  font-size: 0.84rem;
  font-weight: 600;
}

.note-close {
  display: grid;
  flex: none;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  color: rgb(var(--c-fg) / var(--fg-55));
}

.note-close:hover {
  background: rgb(var(--c-tint) / 0.08);
  color: rgb(var(--c-fg));
}

.note-enter-active,
.note-leave-active {
  transition:
    opacity 0.18s ease,
    transform 0.18s ease;
}

.note-enter-from,
.note-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

@media (width <= 700px) {
  .note {
    margin: 0 16px 10px;
    flex-wrap: wrap;
  }
}
</style>
