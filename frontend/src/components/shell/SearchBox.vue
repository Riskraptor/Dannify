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
      <kbd class="kbd">Ctrl</kbd><kbd class="kbd">K</kbd>
    </span>
    <span v-else-if="searching" class="sbx-busy"><span class="spinner h-3.5 w-3.5" /></span>
    <button
      v-else-if="query"
      class="sbx-clear"
      :title="t('search.clear')"
      @mousedown.prevent
      @click="clear"
    >
      <Icon icon="ph:x" class="h-3.5 w-3.5" />
    </button>

    <!-- Suggestions: recent searches -->
    <div
      v-if="focused && suggestions.length"
      class="sbx-pop menu-surface"
      @mousedown.prevent
    >
      <p class="sbx-pop-head">{{ t('search.recent') }}</p>
      <button
        v-for="(s, i) in suggestions"
        :key="s.value + i"
        class="sbx-item"
        :class="{ 'is-active': i === active }"
        @mouseenter="active = i"
        @click="submit(s.value)"
      >
        <Icon :icon="s.icon" class="h-4 w-4 shrink-0 text-fg/50" />
        <span class="min-w-0 flex-1 truncate">{{ s.label }}</span>
        <span
          v-if="s.removable"
          class="sbx-remove"
          role="button"
          :title="t('search.removeRecent')"
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
import { useUi } from '/src/model/ui'
import { useRecent } from '/src/model/recent'
import { useSearchManager } from '/src/model/search'
import { useSearchState } from '/src/model/explore'
import { useI18n } from '/src/i18n'

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

const suggestions = computed(() => {
  const needle = (query.value || '').trim().toLowerCase()
  return recent.searches.value
    .filter((s) => !needle || (s.toLowerCase().includes(needle) && s.toLowerCase() !== needle))
    .slice(0, 6)
    .map((s) => ({ value: s, label: s, icon: 'ph:clock-counter-clockwise', removable: true }))
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
  color: rgb(var(--c-fg) / 0.55);
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
  color: rgb(var(--c-fg) / 0.45);
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
  color: rgb(var(--c-fg) / 0.6);
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
  color: rgb(var(--c-fg) / 0.45);
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
.sbx-remove {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 4px;
  color: rgb(var(--c-fg) / 0.5);
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
