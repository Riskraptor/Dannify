<template>
  <div class="pb-12">
    <ViewHeader
      :title="t('history.title')"
      :tile="{ icon: 'ph:clock-counter-clockwise-bold', kind: 'tile-history' }"
    >
      <template #meta>
        <template v-if="total">{{ t('history.count', { count: total }) }}</template>
        <template v-else>{{ t('history.subtitle') }}</template>
      </template>
      <template #actions>
        <router-link :to="{ name: 'Stats' }" class="btn btn-pill">
          <Icon icon="ph:chart-bar" class="h-4 w-4" />
          {{ t('stats.nav') }}
        </router-link>
        <button v-if="total" class="btn-ghost btn-pill" @click="clearAll">
          <Icon icon="ph:trash" class="h-4 w-4" />
          {{ t('history.clear') }}
        </button>
      </template>
    </ViewHeader>

    <div class="view-pad">
      <div v-if="!listens.keeping.value" class="hist-off">
        <Icon icon="ph:pause-circle" class="h-5 w-5 shrink-0" />
        <p class="min-w-0 flex-1">{{ t('stats.off') }}</p>
        <button class="btn btn-pill h-7 text-xs" @click="listens.setKeeping(true)">{{ t('stats.turnOn') }}</button>
      </div>

      <div v-if="state === 'loading'" class="space-y-2 pt-2">
        <div v-for="n in 8" :key="n" class="skeleton h-12" />
      </div>

      <EmptyState v-else-if="state === 'error' && !items.length" icon="ph:cloud-warning" :title="t('stats.failed')">
        <button class="btn-accent btn-pill press" @click="reload">
          <Icon icon="ph:arrows-clockwise" class="h-4 w-4" />
          {{ t('common.retry') }}
        </button>
      </EmptyState>

      <EmptyState
        v-else-if="!items.length"
        icon="ph:clock-counter-clockwise"
        :title="t('history.emptyTitle')"
        :text="t('history.emptyText')"
      >
        <button class="btn-accent btn-pill" @click="ui.focusSearch()">
          <Icon icon="ph:magnifying-glass" class="h-4 w-4" />
          {{ t('nav.browse') }}
        </button>
      </EmptyState>

      <template v-else>
        <section v-for="group in groups" :key="group.day" class="day">
          <h2 class="day-title">{{ group.title }}</h2>
          <TrackTable
            :rows="group.rows"
            :header="false"
            :show-index="false"
            show-added
            :added-format="clockTime"
            :on-play="(i) => playRows(rows, group.from + i)"
            :on-remove="removeRows"
            :menu-context="{ history: { remove: removeRows }, source: rows }"
          />
        </section>
        <button v-if="more" class="more-btn" :disabled="busy" @click="loadMore">
          <span v-if="busy" class="spinner h-3.5 w-3.5" />
          {{ t('history.more') }}
        </button>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, shallowRef, computed, watch, onActivated, onDeactivated } from 'vue'
import { Icon } from '@iconify/vue'
import { useListens } from '/src/model/listens'
import { useLibrary } from '/src/model/library'
import { useUi } from '/src/model/ui'
import { entryRow } from '/src/model/playlists'
import { playRows } from '/src/model/tracks'
import { confirmDialog } from '/src/model/dialog'
import { toast } from '/src/model/toast'
import { onRefresh } from '/src/model/useRefresh'
import { useI18n } from '/src/i18n'
import ViewHeader from '/src/components/ui/ViewHeader.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'
import TrackTable from '/src/components/ui/TrackTable.vue'

// Everything that was listened to, newest first, a day at a time. "Jump back
// in" on Home is the last few of these; this is all of them.

const { t, locale } = useI18n()
const ui = useUi()
const lib = useLibrary()
const listens = useListens()

lib.ensureLoaded()

const PAGE = 100
const items = shallowRef([])
const total = ref(0)
const more = ref(false)
const state = ref('loading') // loading | ready | error
const busy = ref(false)
let seenEpoch = -1
let asked = 0

// From the top again, as far down as was already showing: the song that has
// just ended goes on top without the list snapping back to one page.
async function reload() {
  const mine = ++asked
  seenEpoch = listens.listensEpoch.value
  try {
    const got = await listens.fetchHistory(Math.min(500, Math.max(PAGE, items.value.length)))
    if (mine !== asked) return
    items.value = got.items || []
    total.value = got.total || 0
    more.value = !!got.more
    state.value = 'ready'
  } catch {
    if (mine === asked) state.value = items.value.length ? 'ready' : 'error'
  }
}

async function loadMore() {
  const last = items.value[items.value.length - 1]
  if (!last || busy.value) return
  const mine = asked
  busy.value = true
  try {
    const got = await listens.fetchHistory(PAGE, last.at)
    // The list was read again from the top meanwhile: this page is of the
    // old one.
    if (mine !== asked) return
    items.value = items.value.concat(got.items || [])
    more.value = !!got.more
  } catch {
    toast(t('stats.failed'), { tone: 'error' })
  } finally {
    busy.value = false
  }
}

reload()
let active = true
watch(listens.listensEpoch, () => {
  if (active) reload()
})
onActivated(() => {
  active = true
  if (seenEpoch !== listens.listensEpoch.value) reload()
})
onDeactivated(() => {
  active = false
})
onRefresh(reload)

// One flat list of rows (what plays on from the one that is clicked), and
// the same rows cut into days for showing.
const rows = computed(() => {
  // Made again when the library is read: a song saved since plays from disk.
  void lib.tracks.value
  return items.value.map((item, i) => ({
    ...entryRow(item, i),
    key: `h:${item.at}:${item.key}`,
    added: item.at,
    listen: { at: item.at, key: item.key },
  }))
})

const dayName = computed(
  () => new Intl.DateTimeFormat(locale.value, { weekday: 'long', day: 'numeric', month: 'long' })
)
const dayNameYear = computed(
  () => new Intl.DateTimeFormat(locale.value, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
)
const clock = computed(() => new Intl.DateTimeFormat(locale.value, { hour: 'numeric', minute: '2-digit' }))
function clockTime(at) {
  return at ? clock.value.format(new Date(at * 1000)) : ''
}

function dayOf(at) {
  const d = new Date(at * 1000)
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}
function dayTitle(day, today) {
  const ago = Math.round((today - day) / 86400000)
  if (ago === 0) return t('history.today')
  if (ago === 1) return t('history.yesterday')
  return (day.getFullYear() === today.getFullYear() ? dayName.value : dayNameYear.value).format(day)
}

const groups = computed(() => {
  const today = dayOf(Date.now() / 1000)
  const out = []
  rows.value.forEach((row, i) => {
    const day = dayOf(row.added)
    const stamp = day.getTime()
    let group = out[out.length - 1]
    if (!group || group.day !== stamp) {
      group = { day: stamp, title: dayTitle(day, today), from: i, rows: [] }
      out.push(group)
    }
    group.rows.push(row)
  })
  return out
})

async function removeRows(chosen) {
  const gone = (chosen || []).filter((r) => r && r.listen)
  if (!gone.length) return
  let removed = 0
  for (const row of gone) {
    try {
      if (await listens.forgetListen(row.listen)) removed++
    } catch {
      // counted below: whatever could not go is still in the list
    }
  }
  if (removed < gone.length) toast(t('history.removeFailed'), { tone: 'error' })
  // The list reads itself again as the history changes (see the watch above).
}

async function clearAll() {
  const ok = await confirmDialog({
    title: t('history.clearTitle'),
    message: t('history.clearText'),
    confirmText: t('history.clear'),
    danger: true,
    icon: 'ph:trash',
  })
  if (!ok) return
  try {
    await listens.clearListens()
    items.value = []
    total.value = 0
    more.value = false
    toast(t('history.cleared'), { icon: 'ph:trash' })
  } catch {
    toast(t('history.clearFailed'), { tone: 'error' })
  }
}
</script>

<style scoped>
.hist-off {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgb(var(--c-warn) / 0.12);
  font-size: 13px;
}
.day {
  margin-bottom: 22px;
}
.day-title {
  margin-bottom: 4px;
  font-size: 15px;
  font-weight: 700;
}
.more-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 13px;
  font-weight: 700;
  color: rgb(var(--c-fg) / var(--fg-60));
}
.more-btn:hover:not(:disabled) {
  color: rgb(var(--c-fg));
  text-decoration: underline;
}
</style>
