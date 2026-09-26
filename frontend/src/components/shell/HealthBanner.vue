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
 *
 * Where there is a fix, it is a button here too. Saved tracks that will not
 * play are repaired from this banner in one press, and it shows how that is
 * going and how it went.
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { t } from '/src/i18n'
import { failedRepairs, reasonText, useRepair } from '/src/model/repair'

const problems = ref([])
const dismissed = ref(false)
const repair = useRepair()

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
// changes it every few seconds, and every check reads every saved track.
let soon = null
function checkSoon() {
  clearTimeout(soon)
  soon = setTimeout(check, 1500)
}

function messageFor(p) {
  if (p.code === 'music_locked') {
    // Not repairable means there is no working key at all, and a repair
    // could not seal what it downloaded. That is a different sentence.
    return p.repairable === false
      ? t('health.keyUnreadable')
      : t('health.musicLocked', { count: p.tracks })
  }
  if (p.code === 'tracks_damaged') return t('health.tracksDamaged', { count: p.tracks })
  if (p.code === 'no_key') return t('health.noKey')
  if (p.code === 'folder_missing') return t('health.folderMissing', { path: p.path })
  if (p.code === 'folder_read_only') return t('health.folderReadOnly', { path: p.path })
  if (p.code === 'check_failed') return t('health.checkFailed')
  if (p.code === 'update_failed') {
    return t('health.updateFailed', { wanted: p.wanted, running: p.running })
  }
  return ''
}

// How many saved tracks the backend says it can repair right now.
const broken = computed(() =>
  problems.value
    .filter((p) => (p.code === 'music_locked' || p.code === 'tracks_damaged') && p.repairable)
    .reduce((n, p) => n + (p.tracks || 0), 0)
)

const round = computed(() => repair.status.value)
const running = computed(() => !!round.value.running)
// A round of one is reported where it was started, next to the track. A
// bigger one is reported here, and stays until dismissed: the problems it
// fixed have left the list above, and a banner that simply vanished would
// read as though nothing had happened.
const finished = computed(() => !running.value && round.value.total > 1)

const current = computed(() => {
  const items = Object.values(round.value.items || {})
  return items.find((i) => i.state === 'working') || null
})
const place = computed(() => Math.min(round.value.done + 1, round.value.total))
const percent = computed(() => {
  const total = round.value.total || 1
  const partial = current.value ? (current.value.progress || 0) / 100 : 0
  return Math.min(100, Math.round(((round.value.done + partial) / total) * 100))
})

const summary = computed(() => {
  const r = round.value
  if (!r.failed) return t('repair.doneAll', { count: r.fixed || r.total })
  let text = `${t('repair.doneSome', { fixed: r.fixed, total: r.total })} ${t(
    'repair.failedSome',
    { count: r.failed }
  )}`
  // One reason for all of them is worth saying: "no internet" is the fix.
  const reasons = new Set(
    Object.values(r.items || {})
      .filter((i) => i.state === 'failed')
      .map((i) => i.reason)
  )
  if (reasons.size === 1) text += ` ${reasonText([...reasons][0])}`
  return text
})
const allGood = computed(
  () => !problems.value.length && finished.value && !round.value.failed
)

// A round starting or finishing is news, whatever was dismissed before.
watch(running, () => {
  dismissed.value = false
})

// Good news does not need to stay at the top of every page. Anything that
// failed does, until somebody closes it.
let fade = null
watch(allGood, (good) => {
  clearTimeout(fade)
  if (good) fade = setTimeout(() => (dismissed.value = true), 15000)
})

const visible = computed(
  () => !dismissed.value && (problems.value.length > 0 || running.value || finished.value)
)

function retryFailed() {
  repair.repairFiles(failedRepairs())
}

// Registered on mount and taken off again on unmount. Toggling the mini player
// unmounts the whole shell, so a listener added at module scope would be added
// again every time and the check would run once per toggle, for ever.
onMounted(() => {
  check()
  window.addEventListener('dannify:library-changed', checkSoon)
})
onUnmounted(() => {
  clearTimeout(soon)
  clearTimeout(fade)
  window.removeEventListener('dannify:library-changed', checkSoon)
})
</script>

<template>
  <div v-if="visible" class="health" :class="{ 'is-good': allGood }" :role="allGood ? 'status' : 'alert'">
    <span class="health-mark" aria-hidden="true">
      <Icon v-if="allGood" icon="ph:check-bold" class="h-3 w-3" />
      <template v-else>!</template>
    </span>
    <div class="health-text">
      <p v-for="p in problems" :key="p.code">{{ messageFor(p) }}</p>

      <div v-if="running" class="health-repair">
        <span class="health-now">
          {{ t('repair.progress', { done: place, total: round.total }) }}
        </span>
        <span class="health-bar" role="progressbar" :aria-valuenow="percent" aria-valuemin="0" aria-valuemax="100">
          <span :style="{ width: `${percent}%` }" />
        </span>
        <button class="health-link" @click="repair.stopRepairs()">{{ t('repair.stop') }}</button>
      </div>

      <!-- What went wrong last time stays until it is dealt with. "Try
           again" takes everything still broken, not only what failed: a
           track that broke since needs it just as much. -->
      <div v-else-if="finished && round.failed" class="health-repair">
        <span>{{ summary }}</span>
        <button
          class="btn-accent btn-pill press health-btn"
          @click="broken > 0 ? repair.repairAll() : retryFailed()"
        >
          <Icon icon="ph:arrows-clockwise" class="h-4 w-4" />
          {{ t('repair.retry') }}
        </button>
      </div>

      <!-- Something broken and nothing running: the offer. It comes before
           a finished round's good news, which is old news by then. -->
      <div v-else-if="broken > 0" class="health-repair">
        <button class="btn-accent btn-pill press health-btn" @click="repair.repairAll()">
          <Icon icon="ph:wrench" class="h-4 w-4" />
          {{ broken > 1 ? t('repair.all') : t('repair.action') }}
        </button>
        <span class="health-hint">{{ t('repair.hint', { count: broken }) }}</span>
      </div>

      <div v-else-if="finished" class="health-repair">
        <span>{{ summary }}</span>
      </div>
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

.health.is-good {
  border-color: rgb(var(--c-accent) / 0.4);
  background: rgb(var(--c-accent) / 0.1);
}

.health-mark {
  display: grid;
  place-items: center;
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

.is-good .health-mark {
  background: rgb(var(--c-accent));
  color: rgb(var(--c-accent-fg));
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

.health-repair {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin-top: 10px;
}

.health-text p + .health-repair {
  margin-top: 10px;
}

.health-text > .health-repair:first-child {
  margin-top: 0;
}

.health-btn {
  height: 30px;
  padding: 0 14px;
  gap: 6px;
  font-size: 0.84rem;
  font-weight: 600;
}

.health-hint {
  opacity: 0.7;
  font-size: 0.84rem;
}

.health-now {
  font-variant-numeric: tabular-nums;
}

.health-bar {
  position: relative;
  flex: 1;
  min-width: 80px;
  max-width: 260px;
  height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.15);
}

.health-bar > span {
  position: absolute;
  inset: 0 auto 0 0;
  border-radius: inherit;
  background: rgb(var(--c-accent));
  transition: width 0.3s ease;
}

.health-link {
  border: 0;
  background: none;
  color: inherit;
  opacity: 0.75;
  font-size: 0.84rem;
  text-decoration: underline;
  text-underline-offset: 2px;
  cursor: pointer;
  padding: 0;
}

.health-link:hover {
  opacity: 1;
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
