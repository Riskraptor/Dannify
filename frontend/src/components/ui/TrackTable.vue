<template>
  <div
    ref="root"
    class="tt"
    :class="{ 'is-dense': !showCover, 'has-bar': barShown }"
    :style="{ '--tt-cols': gridCols, '--tt-sticky': `${stickyOffset}px` }"
    tabindex="0"
    role="grid"
    :aria-rowcount="shown.length"
    :aria-multiselectable="true"
    @keydown="onKey"
    @focusin="focused = true"
    @focusout="onFocusOut"
  >
    <div v-if="header" class="tt-head" role="row">
      <div v-if="selectable" class="tt-cell tt-c-check">
        <input
          type="checkbox"
          class="check"
          tabindex="-1"
          :checked="picking && allSelected"
          :indeterminate.prop="picking && someSelected"
          :aria-label="t('table.selectAll')"
          @change="tickAll"
        />
      </div>
      <div v-if="showIndex" class="tt-cell tt-c-index">#</div>
      <button
        class="tt-cell tt-sort"
        :class="sortClass('title')"
        :disabled="!sortable"
        @click="emit('sort', 'title')"
      >
        {{ t('table.title') }}<SortArrow v-if="sortKey === 'title'" :dir="sortDir" />
      </button>
      <button
        v-if="cols.album"
        class="tt-cell tt-sort"
        :class="sortClass('album')"
        :disabled="!sortable"
        @click="emit('sort', 'album')"
      >
        {{ t('table.album') }}<SortArrow v-if="sortKey === 'album'" :dir="sortDir" />
      </button>
      <button
        v-if="cols.added"
        class="tt-cell tt-sort"
        :class="sortClass('added')"
        :disabled="!sortable"
        @click="emit('sort', 'added')"
      >
        {{ t('table.dateAdded') }}<SortArrow v-if="sortKey === 'added'" :dir="sortDir" />
      </button>
      <button
        class="tt-cell tt-sort tt-c-duration"
        :class="sortClass('duration')"
        :disabled="!sortable"
        :title="t('table.duration')"
        @click="emit('sort', 'duration')"
      >
        <SortArrow v-if="sortKey === 'duration'" :dir="sortDir" />
        <Icon icon="ph:clock" class="h-4 w-4" />
      </button>
    </div>

    <VirtualList
      ref="list"
      :items="shown"
      :item-height="rowHeight"
      :scroller="scroller"
      :item-key="(r) => r.key"
    >
      <template #default="{ item: row, index }">
        <div
          class="tt-row"
          role="row"
          :aria-selected="selected.has(row.key)"
          :class="{
            'is-selected': selected.has(row.key),
            'is-current': isRowCurrent(row),
            'is-cursor': focused && cursor === index,
            'is-broken': !!row.problem,
          }"
          @mousedown="onRowDown($event, index)"
          @click="onRowClick($event, index)"
          @dblclick="onRowDblClick($event, index)"
          @contextmenu="onRowMenu($event, index)"
          @mouseenter="warmOnHover(row.raw)"
          @mouseleave="cancelHoverWarm()"
        >
          <div v-if="selectable" class="tt-cell tt-c-check">
            <input
              type="checkbox"
              class="check"
              tabindex="-1"
              :checked="picking && selected.has(row.key)"
              @mousedown.stop
              @click.stop="tick(index)"
            />
          </div>
          <div v-if="showIndex" class="tt-cell tt-c-index">
            <span
              v-if="isRowCurrent(row) && player.isPlaying.value"
              class="equalizer tt-eq"
              aria-hidden="true"
              ><span /><span /><span
            /></span>
            <span v-else class="tt-num">{{ useTrackNumbers && row.raw && row.raw.track_number ? row.raw.track_number : index + 1 }}</span>
            <button
              class="tt-play"
              tabindex="-1"
              :title="isRowCurrent(row) && player.isPlaying.value ? t('player.pause') : t('player.play')"
              @mousedown.stop
              @click.stop="play(index)"
            >
              <Icon
                :icon="isRowCurrent(row) && player.isPlaying.value ? 'ph:pause-fill' : 'ph:play-fill'"
                class="h-4 w-4"
              />
            </button>
          </div>
          <div class="tt-cell tt-c-title">
            <!-- With no index column the artwork becomes the play button, so
                 the row still has a visible way to start. Where there IS an
                 index the number already does that job, and a second glyph
                 on the cover would just be a duplicate. -->
            <div v-if="showCover" class="tt-art">
              <CoverImage :src="row.cover" radius="sm" :size="40" class="tt-cover" />
              <button
                v-if="!showIndex"
                class="tt-art-play"
                :class="{ 'is-on': isRowCurrent(row) }"
                tabindex="-1"
                :title="isRowCurrent(row) && player.isPlaying.value ? t('player.pause') : t('player.play')"
                @mousedown.stop
                @click.stop="play(index)"
              >
                <span
                  v-if="isRowCurrent(row) && player.isPlaying.value"
                  class="equalizer"
                  aria-hidden="true"
                ><span /><span /><span /></span>
                <Icon v-else icon="ph:play-fill" class="h-4 w-4" />
              </button>
            </div>
            <div class="min-w-0">
              <div class="tt-title" :title="row.title">{{ row.title }}</div>
              <div class="tt-sub">
                <span v-if="row.explicit" class="explicit" :title="t('table.explicit')">E</span>
                <ArtistLinks :artists="row.artists" class="truncate" />
              </div>
            </div>
          </div>
          <div v-if="cols.album" class="tt-cell tt-c-album">
            <a
              v-if="row.album"
              class="link truncate"
              @mousedown.stop
              @click.stop="goToAlbum(row)"
              @dblclick.stop
            >{{ row.album }}</a>
          </div>
          <div v-if="cols.added" class="tt-cell tt-c-added">{{ formatAdded(row.added) }}</div>
          <div class="tt-cell tt-c-duration">
            <button
              v-if="videoIdOf(row)"
              class="icon-btn h-7 w-7 press"
              :class="account.isLiked(videoIdOf(row)) ? 'tt-liked' : 'tt-hover'"
              tabindex="-1"
              :title="account.isLiked(videoIdOf(row)) ? t('account.removeFromLiked') : t('account.addToLiked')"
              @mousedown.stop
              @click.stop="account.toggleLike(row.raw)"
            >
              <Icon
                :icon="account.isLiked(videoIdOf(row)) ? 'ph:heart-fill' : 'ph:heart'"
                class="h-4 w-4"
              />
            </button>
            <span class="tt-status">
              <!-- A saved track that will not play: how its repair is going,
                   or the button that starts one. -->
              <span
                v-if="fixState(row) === 'working'"
                class="spinner h-3.5 w-3.5 border-[1.5px] text-accent"
                :title="t('repair.working')"
              />
              <Icon
                v-else-if="fixState(row) === 'queued'"
                icon="ph:clock"
                class="h-4 w-4 tt-waiting"
                :title="t('repair.queued')"
              />
              <button
                v-else-if="fixState(row) === 'broken'"
                class="icon-btn h-7 w-7 text-danger hover:text-danger"
                tabindex="-1"
                :title="fixTitle(row)"
                :aria-label="t('repair.track')"
                @mousedown.stop
                @click.stop="repairRows([row])"
              >
                <Icon icon="ph:wrench" class="h-4 w-4" />
              </button>
              <span
                v-else-if="dlState(row) === 'active'"
                class="spinner h-3.5 w-3.5 border-[1.5px] text-accent"
                :title="t('downloads.statusDownloading')"
              />
              <Icon
                v-else-if="dlState(row) === 'done'"
                icon="ph:check-circle-fill"
                class="h-4 w-4 text-accent"
                :title="t('search.downloaded')"
              />
              <button
                v-else-if="dlState(row) === 'error'"
                class="icon-btn h-7 w-7 text-danger hover:text-danger"
                tabindex="-1"
                :title="t('downloads.failedRetry')"
                @mousedown.stop
                @click.stop="retryDownload(row)"
              >
                <Icon icon="ph:warning-circle" class="h-4 w-4" />
              </button>
              <button
                v-else-if="row.kind === 'song'"
                class="tt-hover icon-btn h-7 w-7"
                tabindex="-1"
                :title="t('actions.download')"
                @mousedown.stop
                @click.stop="downloadRows([row])"
              >
                <Icon icon="ph:download-simple" class="h-4 w-4" />
              </button>
            </span>
            <span class="tt-time">{{ row.duration ? formatTime(row.duration) : '' }}</span>
            <button
              class="tt-hover icon-btn h-7 w-7"
              tabindex="-1"
              :title="t('actions.more')"
              @mousedown.stop
              @click.stop="onMore($event, index)"
            >
              <Icon icon="ph:dots-three-bold" class="h-4 w-4" />
            </button>
          </div>
        </div>
      </template>
    </VirtualList>

    <!-- What can be done with the ticked songs. It used to take a right-click
         on a selection nobody could see how to make; now ticking a box brings
         this up, and it stays in view while the list scrolls. -->
    <transition name="selbar">
      <div v-if="barShown" class="selbar" role="toolbar" @mousedown.stop>
        <span class="selbar-count">{{ t('selection.count', { count: selectedRows.length }) }}</span>
        <button class="selbar-btn" @click="playRows(selectedRows, 0, { toggle: false })">
          <Icon icon="ph:play-fill" class="h-4 w-4" />
          <span>{{ t('actions.play') }}</span>
        </button>
        <button class="selbar-btn" @click="addToQueue(selectedRows)">
          <Icon icon="ph:list-plus" class="h-4 w-4" />
          <span>{{ t('actions.addToQueue') }}</span>
        </button>
        <button
          v-if="selectedLocals.length"
          class="selbar-btn"
          :disabled="detailsRunning"
          @click="refreshRowDetails(selectedLocals)"
        >
          <Icon icon="ph:arrows-clockwise" class="h-4 w-4" :class="{ 'animate-spin': detailsRunning }" />
          <span>{{
            detailsRunning
              ? t('details.progress', { done: detailsDone, total: detailsTotal })
              : t('details.refresh')
          }}</span>
        </button>
        <button
          v-if="deletable && selectedLocals.length"
          class="selbar-btn is-danger"
          @click="deleteSelected"
        >
          <Icon icon="ph:trash" class="h-4 w-4" />
          <span>{{ t('common.delete') }}</span>
        </button>
        <button class="selbar-close" :title="t('selection.clear')" @click="clearSelection">
          <Icon icon="ph:x-bold" class="h-4 w-4" />
        </button>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, watch, inject, onMounted, onBeforeUnmount, onActivated, onDeactivated, h } from 'vue'
import { Icon } from '@iconify/vue'
import VirtualList from './VirtualList.vue'
import CoverImage from './CoverImage.vue'
import ArtistLinks from './ArtistLinks.vue'
import { usePlayer, formatTime } from '/src/model/player'
import { useAccount } from '/src/model/account'
import { useLibraryIndex } from '/src/model/libraryIndex'
import { useProgressTracker, useDownloadManager } from '/src/model/download'
import { openContextMenu } from '/src/model/contextMenu'
import { cancelHoverWarm, warmOnHover } from '/src/model/prefetch'
import {
  trackMenu,
  playRows,
  isRowCurrent,
  downloadRows,
  deleteRows,
  goToAlbum,
  songVideoId,
  needsRepair,
  offerRepair,
  repairRows,
  addToQueue,
  refreshRowDetails,
} from '/src/model/tracks'
import { repairItemOf, reasonText } from '/src/model/repair'
import { detailsRunning, detailsDone, detailsTotal } from '/src/model/details'
import { useI18n, currentLocale } from '/src/i18n'

const props = defineProps({
  rows: { type: Array, required: true },
  showIndex: { type: Boolean, default: true },
  showCover: { type: Boolean, default: true },
  showAlbum: { type: Boolean, default: true },
  showAdded: { type: Boolean, default: false },
  useTrackNumbers: { type: Boolean, default: false },
  header: { type: Boolean, default: true },
  sortable: { type: Boolean, default: false },
  sortKey: { type: String, default: '' },
  sortDir: { type: String, default: 'asc' },
  selectable: { type: Boolean, default: false }, // checkbox column
  // A bar of actions for the ticked rows (play, queue, refresh, delete).
  selectionBar: { type: Boolean, default: false },
  deletable: { type: Boolean, default: false }, // Delete key removes local files
  stickyOffset: { type: Number, default: 0 },
  // Custom play handler(index). Defaults to "replace the queue with rows".
  onPlay: { type: Function, default: null },
  menuContext: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['sort', 'selection-change'])

const { t } = useI18n()
const player = usePlayer()
const account = useAccount()
const libIndex = useLibraryIndex()
const tracker = useProgressTracker()
const scroller = inject('viewScroller', ref(null))

const root = ref(null)
const list = ref(null)
const focused = ref(false)
const width = ref(1000)
// Keys unique within this list. A YouTube playlist can hold the same video
// twice, and two rows sharing a key were selected, highlighted and redrawn as
// one: clicking either lit both, and "Select all" could never be undone.
const shown = computed(() => {
  const seen = new Map()
  return props.rows.map((r) => {
    const n = seen.get(r.key) || 0
    seen.set(r.key, n + 1)
    return n ? { ...r, key: `${r.key}#${n}` } : r
  })
})

const selected = ref(new Set())
const cursor = ref(-1)
let anchor = -1

const rowHeight = computed(() => (props.showCover ? 56 : 44))

const cols = computed(() => ({
  album: props.showAlbum && width.value >= 560,
  added: props.showAdded && width.value >= 760,
}))

const gridCols = computed(() => {
  const parts = []
  if (props.selectable) parts.push('20px')
  if (props.showIndex) parts.push('28px')
  parts.push('minmax(0, 4fr)')
  if (cols.value.album) parts.push('minmax(0, 3fr)')
  if (cols.value.added) parts.push('minmax(0, 1.5fr)')
  parts.push('144px') // like + download state + time + overflow menu
  return parts.join(' ')
})

// ----- selection ------------------------------------------------------------
const selectedRows = computed(() => shown.value.filter((r) => selected.value.has(r.key)))
const selectedLocals = computed(() => selectedRows.value.filter((r) => r.kind === 'local' && r.file))

async function deleteSelected() {
  if (await deleteRows(selectedLocals.value)) clearSelection()
}
const allSelected = computed(
  () => shown.value.length > 0 && selected.value.size === shown.value.length
)
const someSelected = computed(() => selected.value.size > 0 && !allSelected.value)

function setSelection(keys) {
  selected.value = new Set(keys)
}
function selectOnly(i) {
  ticked.value = false
  anchor = i
  cursor.value = i
  setSelection([shown.value[i].key])
}
function toggleOne(i) {
  ticked.value = true
  const key = shown.value[i].key
  const next = new Set(selected.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  anchor = i
  cursor.value = i
  setSelection(next)
}
function selectRange(i) {
  ticked.value = true
  const from = anchor < 0 ? i : anchor
  const [a, b] = from < i ? [from, i] : [i, from]
  cursor.value = i
  setSelection(shown.value.slice(a, b + 1).map((r) => r.key))
}
// Songs picked on purpose: a box ticked, or chosen with Ctrl or Shift.
// Clicking a song selects it too, and that used to count: the bar came up on
// every single click anywhere in a list, for one song that already has its
// own menu, and an online artist's page offered to download "1 chosen".
// The boxes show only what was picked that way: the song a click highlighted
// is not ticked, and ticking a box starts the picking from that box alone.
const ticked = ref(false)
const picking = computed(() => selectedRows.value.length > 0 && (ticked.value || selectedRows.value.length > 1))
const pickedRows = computed(() => (picking.value ? selectedRows.value : []))
watch(pickedRows, (rows, before) => {
  if (rows.length || (before && before.length)) emit('selection-change', rows)
})
function tick(i) {
  if (picking.value) return toggleOne(i)
  ticked.value = true
  anchor = i
  cursor.value = i
  setSelection([shown.value[i].key])
}
function tickAll() {
  const fresh = !picking.value
  ticked.value = true
  if (fresh) setSelection(shown.value.map((r) => r.key))
  else toggleAll()
}
const barShown = computed(() => props.selectionBar && picking.value)
watch(
  () => selected.value.size,
  (n) => {
    if (!n) ticked.value = false
  }
)
// Notifications sit above the bar rather than on top of it.
function markBar(on) {
  document.documentElement.classList.toggle('has-selbar', !!on)
}
watch(barShown, markBar)
onActivated(() => markBar(barShown.value))
onDeactivated(() => markBar(false))
onBeforeUnmount(() => markBar(false))

function toggleAll() {
  setSelection(allSelected.value ? [] : shown.value.map((r) => r.key))
}
function clearSelection() {
  setSelection([])
}

// Keep the selection sane when the list changes (filtering, sorting…).
watch(
  () => shown.value,
  (rows) => {
    if (!selected.value.size) return
    const keys = new Set(rows.map((r) => r.key))
    const kept = [...selected.value].filter((k) => keys.has(k))
    if (kept.length !== selected.value.size) setSelection(kept)
    if (cursor.value >= rows.length) cursor.value = rows.length - 1
  }
)

// ----- mouse ----------------------------------------------------------------
function isInteractive(target) {
  return !!target.closest('a, button, input')
}

function onRowDown(e, i) {
  if (isInteractive(e.target)) return
  if (e.button === 2) {
    // Right-click keeps an existing multi-selection that includes the row,
    // and songs ticked on purpose stay ticked whatever row it is on.
    if (!selected.value.has(shown.value[i].key) && !picking.value) selectOnly(i)
    return
  }
  if (e.button !== 0) return
  if (e.shiftKey) {
    e.preventDefault()
    selectRange(i)
  } else if (e.ctrlKey || e.metaKey) {
    toggleOne(i)
  } else if (!selected.value.has(shown.value[i].key) || selected.value.size > 1) {
    selectOnly(i)
  } else {
    cursor.value = i
    anchor = i
  }
}

function onRowClick(e, i) {
  // Touch screens (phones on the LAN) have no double-click: tap plays.
  if (e.pointerType === 'touch' && !isInteractive(e.target)) play(i)
}

function onRowDblClick(e, i) {
  if (isInteractive(e.target)) return
  play(i)
}

function menuItems(rows = selectedRows.value) {
  return trackMenu(rows, { ...props.menuContext, source: shown.value })
}

// The menu of the row it was opened on. A row outside the songs ticked on
// purpose gets a menu of its own, and the ticks are not thrown away for it.
function menuFor(i) {
  if (!selected.value.has(shown.value[i].key)) {
    if (picking.value) return menuItems([shown.value[i]])
    selectOnly(i)
  }
  return menuItems()
}

function onRowMenu(e, i) {
  openContextMenu(e, menuFor(i))
}

function onMore(e, i) {
  openContextMenu(e, menuFor(i), { anchor: true })
}

function play(i) {
  // Playing a track that cannot play would start it, fail, and skip to the
  // next one: say why and offer the fix instead, and leave the queue alone.
  if (needsRepair(shown.value[i])) {
    offerRepair(shown.value[i])
    return
  }
  if (props.onPlay) props.onPlay(i)
  else playRows(shown.value, i)
}

// ----- keyboard ---------------------------------------------------------------
function moveCursor(to, extend) {
  const n = shown.value.length
  if (!n) return
  const i = Math.max(0, Math.min(n - 1, to))
  if (extend) selectRange(i)
  else selectOnly(i)
  list.value && list.value.scrollToIndex(i, { topInset: props.header ? 36 + props.stickyOffset : 0 })
}

function onKey(e) {
  const n = shown.value.length
  if (!n || e.target !== root.value) return
  const pageRows = Math.max(1, Math.floor(((scroller.value && scroller.value.clientHeight) || 600) / rowHeight.value) - 2)
  switch (e.key) {
    case 'ArrowDown':
      e.preventDefault()
      moveCursor(cursor.value < 0 ? 0 : cursor.value + 1, e.shiftKey)
      break
    case 'ArrowUp':
      e.preventDefault()
      moveCursor(cursor.value < 0 ? 0 : cursor.value - 1, e.shiftKey)
      break
    case 'PageDown':
      e.preventDefault()
      moveCursor(cursor.value + pageRows, e.shiftKey)
      break
    case 'PageUp':
      e.preventDefault()
      moveCursor(cursor.value - pageRows, e.shiftKey)
      break
    case 'Home':
      e.preventDefault()
      moveCursor(0, e.shiftKey)
      break
    case 'End':
      e.preventDefault()
      moveCursor(n - 1, e.shiftKey)
      break
    case 'Enter':
      if (cursor.value >= 0) {
        e.preventDefault()
        play(cursor.value)
      }
      break
    case 'Escape':
      if (selected.value.size) {
        e.preventDefault()
        clearSelection()
      }
      break
    case 'Delete':
      if (props.deletable && selected.value.size) {
        e.preventDefault()
        deleteRows(selectedRows.value)
      }
      break
    case 'a':
    case 'A':
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault()
        ticked.value = true
        setSelection(shown.value.map((r) => r.key))
      }
      break
    case 'ContextMenu':
    case 'F10':
      if (e.key === 'F10' && !e.shiftKey) break
      e.preventDefault()
      if (cursor.value < 0) selectOnly(0)
      {
        const el = root.value.querySelector('.tt-row.is-cursor') || root.value
        openContextMenu({ currentTarget: el, preventDefault() {}, stopPropagation() {} }, menuItems())
      }
      break
    default:
      break
  }
}

function onFocusOut(e) {
  if (!root.value || !root.value.contains(e.relatedTarget)) focused.value = false
}

// ----- cells ----------------------------------------------------------------
// Only YouTube-backed rows can be liked; a local file with no videoId can't.
const videoIdOf = songVideoId

function dlState(row) {
  if (row.kind !== 'song') return 'none'
  if (libIndex.isDownloaded(row.raw)) return 'done'
  const item = tracker.getBySong(row.raw)
  if (!item) return 'none'
  if (item.isErrored()) return 'error'
  // Finished, and the library has been read since without it: the song was
  // deleted, here or in Explorer. It used to keep its check mark regardless,
  // with no Download button, as if it were still saved.
  if (item.isDownloaded()) {
    return libIndex.loadedAt.value > (item.completedAt || 0) ? 'none' : 'done'
  }
  return 'active'
}

// '' for anything that is fine, or not a saved track at all.
function fixState(row) {
  if (row.kind !== 'local') return ''
  const item = repairItemOf(row.file)
  if (item && (item.state === 'queued' || item.state === 'working')) return item.state
  // Repaired, and the library has not been read again yet: no button for
  // the second it takes, or it would offer to fix what was just fixed.
  if (item && (item.state === 'fixed' || item.state === 'fine')) return ''
  return row.problem ? 'broken' : ''
}

function fixTitle(row) {
  const item = repairItemOf(row.file)
  if (item && item.state === 'failed') {
    return t('repair.failedRow', { why: reasonText(item.reason) })
  }
  return t('repair.needs')
}

// Straight to the download manager, as the Downloads page does. Through
// downloadRows it went nowhere: the row had just been marked as on its way,
// and songs already on their way are not sent again, so the retry was
// dropped and the row spun with nothing behind it.
function retryDownload(row) {
  const item = tracker.getBySong(row.raw)
  if (item) {
    item.setDownloading()
    item.progress = 0
    item.message = ''
  }
  useDownloadManager().downloadSongs([row.raw])
}

const rtf = computed(() => new Intl.RelativeTimeFormat(currentLocale.value, { numeric: 'auto' }))
const dtf = computed(
  () => new Intl.DateTimeFormat(currentLocale.value, { day: 'numeric', month: 'short', year: 'numeric' })
)
function formatAdded(ts) {
  if (!ts) return ''
  const ms = ts * 1000
  const days = Math.round((ms - Date.now()) / 86400000)
  if (days > -1) return rtf.value.format(0, 'day')
  if (days > -30) return rtf.value.format(days, 'day')
  return dtf.value.format(new Date(ms))
}

function sortClass(key) {
  return { 'is-sorted': props.sortKey === key, 'is-sortable': props.sortable }
}

const SortArrow = {
  props: { dir: String },
  setup(p) {
    return () =>
      h(Icon, {
        icon: p.dir === 'desc' ? 'ph:caret-down-fill' : 'ph:caret-up-fill',
        class: 'h-3 w-3 text-accent',
      })
  },
}

// ----- sizing ---------------------------------------------------------------
let ro = null
onMounted(() => {
  ro = new ResizeObserver(([entry]) => {
    width.value = entry.contentRect.width
  })
  ro.observe(root.value)
})
onBeforeUnmount(() => ro && ro.disconnect())

defineExpose({ selectedRows, clearSelection, focus: () => root.value && root.value.focus() })
</script>

<style scoped>
.tt {
  position: relative;
  outline: none;
}
/* Always in the same place, just above the player, so notifications can stack
   clear of it (see ToastHost). It used to sit at the end of a short list, in
   the middle of the screen, right where they appear. */
.selbar {
  position: fixed;
  left: 50%;
  bottom: calc(var(--player-h) + 16px);
  z-index: 1040;
  display: flex;
  align-items: center;
  gap: 4px;
  width: max-content;
  max-width: calc(100vw - 32px);
  transform: translateX(-50%);
  padding: 6px 6px 6px 16px;
  border-radius: 999px;
  background: rgb(var(--c-elev));
  border: 1px solid rgb(var(--c-tint) / 0.1);
  box-shadow: var(--shadow-pop);
}
.selbar-count {
  margin-right: 8px;
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.selbar-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  color: rgb(var(--c-fg) / 0.85);
  transition: background-color 0.12s ease, color 0.12s ease;
}
.selbar-btn:hover {
  background: rgb(var(--c-tint) / 0.08);
  color: rgb(var(--c-fg));
}
.selbar-btn.is-danger:hover {
  color: rgb(var(--c-danger));
}
.selbar-close {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  margin-left: 2px;
  border-radius: 999px;
  color: rgb(var(--c-fg) / 0.6);
}
.selbar-close:hover {
  background: rgb(var(--c-tint) / 0.08);
  color: rgb(var(--c-fg));
}
/* Narrow: icons only, so the bar never runs off the edge. */
@media (max-width: 640px) {
  .selbar-btn span {
    display: none;
  }
}
.selbar-enter-active,
.selbar-leave-active {
  transition: opacity 0.16s ease, transform 0.18s var(--ease-out);
}
.selbar-enter-from,
.selbar-leave-to {
  opacity: 0;
  transform: translate(-50%, 10px);
}
/* Room under the last song, so the bar never hides it. */
.tt.has-bar {
  padding-bottom: 72px;
}
.tt-head,
.tt-row {
  display: grid;
  grid-template-columns: var(--tt-cols);
  column-gap: 16px;
  align-items: center;
  padding: 0 12px;
}
.tt-head {
  position: sticky;
  top: var(--tt-sticky);
  z-index: 3;
  height: 36px;
  margin-bottom: 8px;
  border-bottom: 1px solid rgb(var(--c-tint) / 0.08);
  background: rgb(var(--c-panel));
  font-size: 12px;
  font-weight: 500;
  color: rgb(var(--c-fg) / 0.55);
}
.tt-sort {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  height: 100%;
  text-align: left;
}
.tt-sort.is-sortable:hover,
.tt-sort.is-sorted {
  color: rgb(var(--c-fg));
}
.tt-sort:disabled {
  opacity: 1;
}
.tt-row {
  height: calc(100% - 2px);
  margin: 1px 0;
  border-radius: 6px;
  font-size: 14px;
}
.tt-row:hover {
  background: rgb(var(--c-tint) / 0.06);
}
.tt-row.is-selected {
  background: rgb(var(--c-tint) / 0.11);
}
.tt-row.is-cursor {
  box-shadow: inset 0 0 0 1px rgb(var(--c-tint) / 0.25);
}
.tt-cell {
  display: flex;
  align-items: center;
  min-width: 0;
}
.tt-c-index {
  position: relative;
  justify-content: center;
  font-size: 14px;
  color: rgb(var(--c-fg) / 0.55);
  font-variant-numeric: tabular-nums;
}
.tt-head .tt-c-index {
  font-size: 12px;
}
.tt-play {
  position: absolute;
  inset: 0;
  display: none;
  place-items: center;
  color: rgb(var(--c-fg));
}
.tt-row:hover .tt-play {
  display: grid;
}
.tt-row:hover .tt-num,
.tt-row:hover .tt-eq {
  visibility: hidden;
}
.tt-row.is-current .tt-num,
.tt-row.is-current .tt-title {
  color: rgb(var(--c-accent));
}
.tt-c-title {
  gap: 12px;
}
.tt-art {
  position: relative;
  flex-shrink: 0;
  width: 40px;
  height: 40px;
}
.tt-cover {
  width: 40px;
  height: 40px;
}
/* The artwork is the play button: a scrim + glyph fades in on row hover,
   and stays put on the playing row so you can always find your place. */
.tt-art-play {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  border-radius: 4px;
  color: #fff;
  background: rgb(0 0 0 / 0.55);
  opacity: 0;
  transition:
    opacity 0.14s ease,
    background-color 0.14s ease;
}
.tt-art-play > .equalizer span {
  background: #fff;
}
.tt-art-play:hover {
  background: rgb(0 0 0 / 0.66);
}
.tt-art-play:active {
  transform: scale(0.94);
}
.tt-row:hover .tt-art-play,
.tt-row:focus-within .tt-art-play,
.tt-art-play.is-on {
  opacity: 1;
}
.tt-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
  color: rgb(var(--c-fg));
}
.tt-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: 13px;
  color: rgb(var(--c-fg) / 0.58);
}
.tt-sub :deep(.artist-links) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tt-c-album,
.tt-c-added {
  font-size: 13px;
  color: rgb(var(--c-fg) / 0.58);
}
.tt-c-album .link {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tt-c-added {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tt-c-duration {
  justify-content: flex-end;
  gap: 4px;
}
.tt-status {
  display: grid;
  place-items: center;
  width: 28px;
}
.tt-time {
  width: 40px;
  text-align: right;
  font-size: 13px;
  color: rgb(var(--c-fg) / 0.58);
  font-variant-numeric: tabular-nums;
}
.tt-head .tt-c-duration {
  justify-content: flex-end;
  padding-right: 32px;
}
.tt-hover {
  opacity: 0;
}
.tt-row:hover .tt-hover,
.tt-row:focus-within .tt-hover,
.tt-row.is-selected .tt-hover {
  opacity: 1;
}
.tt-liked {
  color: rgb(var(--c-accent));
}
/* A saved track that will not play: still listed, clearly not ready. */
.tt-row.is-broken .tt-title,
.tt-row.is-broken .tt-sub,
.tt-row.is-broken .tt-art {
  opacity: 0.5;
}
.tt-waiting {
  color: rgb(var(--c-fg) / 0.5);
}
.tt-liked:hover {
  color: rgb(var(--c-accent));
}
.tt-c-check {
  justify-content: center;
}
.is-dense .tt-row {
  font-size: 14px;
}
</style>
