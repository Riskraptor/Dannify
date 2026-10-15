<template>
  <Teleport to="body">
    <transition name="cp">
      <div v-if="ui.paletteOpen.value" class="cp-layer" @mousedown.self="close">
        <div
          ref="box"
          class="cp menu-surface"
          role="dialog"
          aria-modal="true"
          :aria-label="t('palette.title')"
          @keydown.stop="onKey"
        >
          <div class="cp-top">
            <Icon icon="ph:command" class="cp-top-icon" />
            <input
              ref="field"
              v-model="query"
              class="cp-input"
              type="text"
              role="combobox"
              aria-expanded="true"
              aria-autocomplete="list"
              :aria-controls="listId"
              :aria-activedescendant="rows.length ? optionId(active) : undefined"
              :aria-label="t('palette.title')"
              :placeholder="t('palette.placeholder')"
              spellcheck="false"
              autocomplete="off"
            />
          </div>
          <div :id="listId" ref="list" class="cp-list" role="listbox" :aria-label="t('palette.title')">
            <template v-for="(row, i) in rows" :key="row.id">
              <!-- Headings only while browsing: once something is typed the
                   list is in order of how well it matches, not by kind. -->
              <p v-if="row.heading" class="cp-group" aria-hidden="true">{{ row.heading }}</p>
              <div
                :id="optionId(i)"
                class="cp-row"
                role="option"
                :aria-selected="i === active"
                :class="{ 'is-active': i === active }"
                @mousemove="active = i"
                @click="run(row)"
              >
                <span v-if="row.swatch" class="cp-swatch" :style="{ background: row.swatch }" aria-hidden="true" />
                <Icon v-else :icon="row.icon" class="cp-icon" />
                <span class="cp-title">{{ row.title }}</span>
                <span v-if="row.hint" class="cp-hint">{{ row.hint }}</span>
                <span v-if="row.keys" class="cp-keys" aria-hidden="true">
                  <kbd v-for="k in row.keys" :key="k" class="kbd">{{ k }}</kbd>
                </span>
              </div>
            </template>
          </div>
          <footer class="cp-foot" aria-hidden="true">
            <span><kbd class="kbd">↑</kbd><kbd class="kbd">↓</kbd> {{ t('palette.hintMove') }}</span>
            <span><kbd class="kbd">Enter</kbd> {{ t('palette.hintRun') }}</span>
            <span><kbd class="kbd">Esc</kbd> {{ t('palette.hintClose') }}</span>
          </footer>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, ref, shallowRef, useId, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import { useUi } from '/src/model/ui'
import { buildCommands } from '/src/model/commands'
import { rankCommands } from '/src/model/commandFilter'
import { useRecent } from '/src/model/recent'
import { rememberFocus } from '/src/model/focusTrap'
import { useI18n } from '/src/i18n'

// The command palette: one box that reaches every place and every action in
// the app from the keyboard. What it offers is in model/commands.js; this is
// only the box, the list and the keys that move through it.

const { t } = useI18n()
const router = useRouter()
const ui = useUi()
const recent = useRecent()

const uid = useId()
const listId = `${uid}-list`
const optionId = (i) => `${uid}-option-${i}`

const box = ref(null)
const field = ref(null)
const list = ref(null)
const query = ref('')
const active = ref(0)
const commands = shallowRef([])
let giveBack = null

const rows = computed(() => {
  const typed = query.value.trim()
  const found = rankCommands(commands.value, typed)
  if (!typed) {
    let last = ''
    return found.map((command) => {
      const heading = command.group !== last ? command.group : ''
      last = command.group
      return { ...command, heading }
    })
  }
  // Whatever was typed can always be looked for as music: the palette never
  // answers with only "nothing matches".
  return found.concat({
    id: 'search-for',
    title: t('palette.searchFor', { query: typed }),
    icon: 'ph:magnifying-glass',
    run: () => {
      recent.rememberSearch(typed)
      router.push({ name: 'Search', params: { query: typed } })
    },
  })
})

function close() {
  ui.paletteOpen.value = false
}

function run(row) {
  if (!row) return
  // Closed first, and the keyboard handed back to where it was: what the
  // command runs may open a dialog of its own, which then takes it from
  // there and returns it to the right place when it is done.
  close()
  nextTick(() => row.run())
}

function move(to) {
  const n = rows.value.length
  if (!n) return
  active.value = (to + n) % n
  nextTick(() => {
    const el = list.value && list.value.querySelector('.cp-row.is-active')
    if (el) el.scrollIntoView({ block: 'nearest' })
  })
}

function onKey(e) {
  if (e.key === 'Escape') {
    e.preventDefault()
    close()
  } else if (e.key === 'ArrowDown') {
    e.preventDefault()
    move(active.value + 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    move(active.value - 1)
  } else if (e.key === 'Home' && !query.value) {
    e.preventDefault()
    move(0)
  } else if (e.key === 'End' && !query.value) {
    e.preventDefault()
    move(rows.value.length - 1)
  } else if (e.key === 'PageDown') {
    e.preventDefault()
    move(Math.min(rows.value.length - 1, active.value + 8))
  } else if (e.key === 'PageUp') {
    e.preventDefault()
    move(Math.max(0, active.value - 8))
  } else if (e.key === 'Enter') {
    e.preventDefault()
    run(rows.value[active.value])
  } else if (e.key === 'Tab') {
    // There is one thing to be on in here, and it is the box.
    e.preventDefault()
    field.value && field.value.focus()
  }
}

// The best match is the one Enter runs, whatever was highlighted before.
watch(query, () => {
  active.value = 0
  if (list.value) list.value.scrollTop = 0
})

watch(
  () => ui.paletteOpen.value,
  async (open) => {
    if (!open) {
      const back = giveBack
      giveBack = null
      back?.()
      return
    }
    giveBack = rememberFocus()
    commands.value = buildCommands()
    query.value = ''
    active.value = 0
    await nextTick()
    field.value && field.value.focus()
  }
)
</script>

<style scoped>
.cp-layer {
  position: fixed;
  inset: 0;
  z-index: 1100;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: min(18vh, 140px) 24px 24px;
  background: rgb(0 0 0 / 0.45);
}
.cp {
  display: flex;
  flex-direction: column;
  width: min(620px, 100%);
  max-height: min(520px, 100%);
  overflow: hidden;
}
.cp-top {
  position: relative;
  flex-shrink: 0;
  border-bottom: 1px solid rgb(var(--c-tint) / 0.08);
}
.cp-top-icon {
  position: absolute;
  left: 16px;
  top: 50%;
  width: 18px;
  height: 18px;
  transform: translateY(-50%);
  color: rgb(var(--c-fg) / var(--fg-50));
  pointer-events: none;
}
.cp-input {
  width: 100%;
  height: 50px;
  padding: 0 16px 0 46px;
  border: 0;
  background: transparent;
  font-size: 15px;
  color: rgb(var(--c-fg));
  outline: none;
}
.cp-input::placeholder {
  color: rgb(var(--c-fg) / var(--fg-45));
}
.cp-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 6px;
}
.cp-group {
  padding: 10px 10px 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgb(var(--c-fg) / var(--fg-45));
}
.cp-row {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 38px;
  padding: 0 10px;
  border-radius: 6px;
  font-size: 13.5px;
}
.cp-row.is-active {
  background: rgb(var(--c-tint) / 0.09);
}
.cp-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  color: rgb(var(--c-fg) / var(--fg-60));
}
.cp-row.is-active .cp-icon {
  color: rgb(var(--c-fg));
}
/* A palette is shown by its own colour, not by a picture of a palette. */
.cp-swatch {
  width: 14px;
  height: 14px;
  margin: 0 2px;
  flex-shrink: 0;
  border-radius: 999px;
  box-shadow: 0 0 0 1px rgb(var(--c-tint) / 0.2);
}
.cp-title {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cp-hint {
  flex-shrink: 0;
  font-size: 12px;
  color: rgb(var(--c-fg) / var(--fg-55));
}
.cp-keys {
  display: flex;
  flex-shrink: 0;
  gap: 3px;
}
.cp-foot {
  display: flex;
  flex-shrink: 0;
  gap: 18px;
  padding: 8px 14px;
  border-top: 1px solid rgb(var(--c-tint) / 0.08);
  background: rgb(var(--c-tint) / 0.03);
  font-size: 11.5px;
  color: rgb(var(--c-fg) / var(--fg-55));
}
.cp-foot span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.cp-enter-active,
.cp-leave-active {
  transition: opacity 0.12s ease;
}
.cp-enter-active .cp,
.cp-leave-active .cp {
  transition: transform 0.16s var(--ease-out);
}
.cp-enter-from,
.cp-leave-to {
  opacity: 0;
}
.cp-enter-from .cp,
.cp-leave-to .cp {
  transform: translateY(-8px) scale(0.985);
}
</style>
