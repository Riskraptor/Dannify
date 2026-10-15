<template>
  <div class="sbx" :class="{ 'is-focused': focused }" data-no-drag>
    <Icon icon="ph:magnifying-glass" class="sbx-icon" />
    <input
      ref="input"
      v-model="query"
      type="text"
      class="sbx-input"
      spellcheck="false"
      autocomplete="off"
      :placeholder="t('search.placeholder')"
      :aria-label="t('nav.search')"
      @focus="onFocus"
      @blur="onBlur"
      @keydown="onKey"
    />
    <span v-if="!query && !focused" class="sbx-hint">
      <kbd class="kbd">{{ platform === 'macos' ? '⌘' : 'Ctrl' }}</kbd><kbd class="kbd">K</kbd>
    </span>
    <span v-else-if="searching" class="sbx-busy"><span class="spinner h-3.5 w-3.5" /></span>
    <button
      v-else-if="query"
      class="sbx-clear"
      :title="t('search.clear')"
      :aria-label="t('search.clear')"
      @mousedown.prevent
      @click="clear"
    >
      <Icon icon="ph:x" class="h-3.5 w-3.5" />
    </button>

    <!-- Suggestions: what was searched for before, then ways YouTube Music
         would finish what is being typed -->
    <div
      v-if="focused && suggestions.length"
      class="sbx-pop menu-surface"
      @mousedown.prevent
    >
      <p v-if="!needle" class="sbx-pop-head">{{ t('search.recent') }}</p>
      <!-- The pointer moving picks a row, not the list opening under a
           pointer that was resting there: that used to move the arrow keys'
           place, and Down then went to the sixth suggestion, not the first. -->
      <button
        v-for="(s, i) in suggestions"
        :key="s.value + i"
        class="sbx-item"
        :class="{ 'is-active': i === active }"
        @mousemove="active = i"
        @click="submit(s.value)"
      >
        <Icon :icon="s.icon" class="h-4 w-4 shrink-0 text-fg/50" />
        <!-- What was typed is already known: the rest is what is offered. -->
        <span class="min-w-0 flex-1 truncate">
          <template v-if="s.typed"><span class="sbx-typed">{{ s.typed }}</span>{{ s.rest }}</template>
          <template v-else>{{ s.label }}</template>
        </span>
        <span
          v-if="s.removable"
          class="sbx-remove"
          role="button"
          :title="t('search.removeRecent')"
          :aria-label="t('search.removeRecent')"
          @click.stop="recent.forgetSearch(s.value)"
        >
          <Icon icon="ph:x" class="h-3.5 w-3.5" />
        </span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { useUi } from '/src/model/ui'
import { useRecent } from '/src/model/recent'
import { useSearchManager } from '/src/model/search'
import { useSearchState } from '/src/model/explore'
import { useI18n } from '/src/i18n'
import { platform } from '/src/desktop/bridge'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const ui = useUi()
const recent = useRecent()
const sm = useSearchManager()
const searchState = useSearchState()

const input = ref(null)
const query = sm.searchTerm // shared with the Search view
const focused = ref(false)
const active = ref(-1)
let liveTimer = null

const searching = computed(() => !!searchState.value.searching)

const needle = computed(() => (query.value || '').trim().toLowerCase())

// Ways to finish what is being typed, from YouTube Music. Asked for a moment
// after each keystroke, and an answer to an earlier one is dropped: typed
// quickly, they would otherwise arrive out of order and offer "sau" its
// completions under "sauti sol".
const online = ref([])
// What they are completions of. Until the answer for what is typed now is
// in, the last one's are kept only where they still fit it.
const onlineFor = ref('')
let suggestTimer = null
let suggestAsk = null
function askSuggestions(text) {
  clearTimeout(suggestTimer)
  if (suggestAsk) suggestAsk.abort()
  suggestAsk = null
  if (!focused.value || text.length < 2) {
    online.value = []
    return
  }
  suggestTimer = setTimeout(async () => {
    const ask = (suggestAsk = typeof AbortController === 'function' ? new AbortController() : null)
    try {
      const res = await API.searchSuggest(text, ask ? ask.signal : undefined)
      if (ask && ask.signal.aborted) return
      online.value = (res.data && res.data.suggestions) || []
      onlineFor.value = text.toLowerCase()
    } catch {
      // Offline, or too slow to be useful: nothing is offered.
    }
  }, 140)
}

const MAX_SUGGESTIONS = 6
const suggestions = computed(() => {
  const typed = needle.value
  const recents = recent.searches.value
    .filter((s) => !typed || (s.toLowerCase().includes(typed) && s.toLowerCase() !== typed))
    .slice(0, typed ? 2 : MAX_SUGGESTIONS)
    .map((s) => ({ value: s, label: s, icon: 'ph:clock-counter-clockwise', removable: true }))
  if (!typed) return recents
  const have = new Set(recents.map((s) => s.value.toLowerCase()))
  const fresh = onlineFor.value === typed
  const more = online.value
    .filter((s) => {
      const low = s.toLowerCase()
      return !have.has(low) && low !== typed && (fresh || low.includes(typed))
    })
    .slice(0, MAX_SUGGESTIONS - recents.length)
    .map((s) => {
      const continues = s.toLowerCase().startsWith(typed)
      return {
        value: s,
        label: s,
        icon: 'ph:magnifying-glass',
        removable: false,
        typed: continues ? s.slice(0, typed.length) : '',
        rest: continues ? s.slice(typed.length) : '',
      }
    })
  return recents.concat(more)
})

function submit(value) {
  const q = String(value ?? query.value ?? '').trim()
  clearTimeout(liveTimer)
  if (!q) return
  query.value = q
  recent.rememberSearch(q)
  goSearch(q, false)
  input.value?.blur()
}

function goSearch(q, replace) {
  const target = { name: 'Search', params: { query: q } }
  if (replace && route.name === 'Search') router.replace(target)
  else router.push(target)
}

// Search-as-you-type (desktop apps don't make you press Enter for every
// keystroke). Short queries wait a little longer to avoid wasted round trips.
watch(query, (q) => {
  active.value = -1
  clearTimeout(liveTimer)
  const text = (q || '').trim()
  askSuggestions(text)
  if (!focused.value || text.length < 2) return
  liveTimer = setTimeout(
    () => goSearch(text, route.name === 'Search'),
    text.length < 4 ? 550 : 320
  )
})

function clear() {
  query.value = ''
  input.value?.focus()
}

function onFocus() {
  focused.value = true
  active.value = -1
  requestAnimationFrame(() => input.value?.select())
}
function onBlur() {
  focused.value = false
  // A search still waiting to go out is dropped with the focus. Left to run,
  // typing and then clicking Library straight away was followed, half a
  // second later, by being taken back to Search.
  clearTimeout(liveTimer)
  clearTimeout(suggestTimer)
}

function onKey(e) {
  const list = suggestions.value
  if (e.key === 'Enter') {
    e.preventDefault()
    const pick = active.value >= 0 ? list[active.value] : null
    submit(pick ? pick.value : query.value)
  } else if (e.key === 'ArrowDown' && list.length) {
    e.preventDefault()
    active.value = (active.value + 1) % list.length
  } else if (e.key === 'ArrowUp' && list.length) {
    e.preventDefault()
    active.value = active.value <= 0 ? list.length - 1 : active.value - 1
  } else if (e.key === 'Escape') {
    e.preventDefault()
    if (query.value) query.value = ''
    else input.value?.blur()
  }
}

watch(
  () => ui.searchFocusTick.value,
  () => input.value?.focus()
)

// Off the search page the box is empty again. The words of the last search
// stayed in it over an artist's page or the library, as if that were what
// they had found. Going back to the results puts them back (the Search page
// reads them from its address).
watch(
  () => route.name,
  (to, from) => {
    if (from === 'Search' && to !== 'Search' && !focused.value) query.value = ''
  }
)
</script>

<style scoped>
.sbx {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
  height: 34px;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.07);
  border: 1px solid transparent;
  transition:
    background-color 0.12s ease,
    border-color 0.12s ease;
}
.sbx:hover {
  background: rgb(var(--c-tint) / 0.1);
}
.sbx.is-focused {
  background: rgb(var(--c-panel));
  border-color: rgb(var(--c-accent) / 0.8);
}
.sbx-icon {
  position: absolute;
  left: 12px;
  width: 17px;
  height: 17px;
  color: rgb(var(--c-fg) / var(--fg-55));
  pointer-events: none;
}
.sbx-input {
  width: 100%;
  height: 100%;
  padding: 0 72px 0 38px;
  background: transparent;
  font-size: 13px;
  color: rgb(var(--c-fg));
  outline: none;
  border: 0;
}
.sbx-input::placeholder {
  color: rgb(var(--c-fg) / var(--fg-45));
}
.sbx-hint {
  position: absolute;
  right: 10px;
  display: flex;
  gap: 3px;
  pointer-events: none;
}
.sbx-busy {
  position: absolute;
  right: 34px;
  display: flex;
  color: rgb(var(--c-accent));
  pointer-events: none;
}
.sbx-clear {
  position: absolute;
  right: 6px;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  color: rgb(var(--c-fg) / var(--fg-60));
}
.sbx-clear:hover {
  background: rgb(var(--c-tint) / 0.1);
  color: rgb(var(--c-fg));
}
.sbx-pop {
  position: absolute;
  left: 0;
  right: 0;
  top: calc(100% + 6px);
  z-index: 60;
  padding: 4px;
}
.sbx-pop-head {
  padding: 6px 10px 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgb(var(--c-fg) / var(--fg-45));
}
.sbx-item {
  display: flex;
  width: 100%;
  height: 34px;
  align-items: center;
  gap: 10px;
  padding: 0 8px 0 10px;
  border-radius: 5px;
  font-size: 13px;
  text-align: left;
}
.sbx-item.is-active {
  background: rgb(var(--c-tint) / 0.08);
}
.sbx-typed {
  color: rgb(var(--c-fg) / var(--fg-58));
}
.sbx-remove {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 4px;
  color: rgb(var(--c-fg) / var(--fg-50));
  opacity: 0;
}
.sbx-item:hover .sbx-remove,
.sbx-item.is-active .sbx-remove {
  opacity: 1;
}
.sbx-remove:hover {
  background: rgb(var(--c-tint) / 0.1);
  color: rgb(var(--c-fg));
}
</style>
