<template>
  <Teleport to="body">
    <div
      v-if="menu"
      class="cm-layer"
      @mousedown.self="close"
      @wheel="close"
      @contextmenu.prevent.self="close"
    >
      <div
        ref="panel"
        :key="menu.id"
        class="cm menu-surface"
        role="menu"
        tabindex="-1"
        :style="style"
        @keydown="onKey"
        @contextmenu.prevent
      >
        <template v-for="(it, i) in menu.items" :key="i">
          <div v-if="it.divider" class="cm-sep" role="separator" />
          <div v-else-if="it.header" class="cm-header">{{ it.header }}</div>
          <button
            v-else
            class="cm-item"
            :class="{ 'is-danger': it.danger, 'is-active': i === active }"
            role="menuitem"
            :disabled="it.disabled"
            @mouseenter="active = i"
            @mouseleave="active = -1"
            @click="run(it)"
          >
            <Icon v-if="it.icon" :icon="it.icon" class="cm-icon" />
            <span v-else class="cm-icon" />
            <span class="cm-label">{{ it.label }}</span>
            <Icon v-if="it.checked" icon="ph:check-bold" class="cm-check" />
            <span v-else-if="it.shortcut" class="cm-shortcut">{{ it.shortcut }}</span>
          </button>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { Icon } from '@iconify/vue'
import { useRoute } from 'vue-router'
import { useContextMenu } from '/src/model/contextMenu'

const { menu, closeContextMenu } = useContextMenu()
const route = useRoute()
const panel = ref(null)
const active = ref(-1)
const style = ref({ left: '0px', top: '0px', visibility: 'hidden' })

const MARGIN = 8

function close() {
  closeContextMenu()
}

function run(item) {
  if (item.disabled) return
  close()
  // Let the menu disappear before the action (dialogs, navigation…).
  requestAnimationFrame(() => item.action && item.action())
}

async function place() {
  style.value = { left: '0px', top: '0px', visibility: 'hidden' }
  active.value = -1
  await nextTick()
  const el = panel.value
  if (!el || !menu.value) return
  const { width, height } = el.getBoundingClientRect()
  const vw = window.innerWidth
  const vh = window.innerHeight
  let x = menu.value.alignRight ? menu.value.x - width : menu.value.x
  let y = menu.value.y
  if (x + width > vw - MARGIN) x = Math.max(MARGIN, menu.value.x - width)
  if (y + height > vh - MARGIN) {
    const flip = typeof menu.value.above === 'number' ? menu.value.above : y
    y = Math.max(MARGIN, flip - height)
  }
  x = Math.min(Math.max(MARGIN, x), vw - width - MARGIN)
  y = Math.min(Math.max(MARGIN, y), vh - height - MARGIN)
  style.value = { left: `${x}px`, top: `${y}px`, visibility: 'visible' }
  el.focus({ preventScroll: true })
}

function step(dir) {
  const items = menu.value ? menu.value.items : []
  if (!items.length) return
  let i = active.value
  for (let n = 0; n < items.length; n++) {
    i = (i + dir + items.length) % items.length
    const it = items[i]
    if (!it.divider && !it.header && !it.disabled) {
      active.value = i
      return
    }
  }
}

function onKey(e) {
  e.stopPropagation()
  if (e.key === 'Escape' || e.key === 'Tab') {
    e.preventDefault()
    close()
  } else if (e.key === 'ArrowDown') {
    e.preventDefault()
    step(1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    step(-1)
  } else if (e.key === 'Home') {
    e.preventDefault()
    active.value = -1
    step(1)
  } else if (e.key === 'End') {
    e.preventDefault()
    active.value = 0
    step(-1)
  } else if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    const it = menu.value && menu.value.items[active.value]
    if (it && !it.divider && !it.header) run(it)
  }
}

watch(
  () => menu.value && menu.value.id,
  (id) => {
    if (id) place()
  }
)
watch(() => route.fullPath, close)

function onBlur() {
  close()
}
// Escape closes it even when the focus went somewhere else first.
function onWindowKey(e) {
  if (menu.value && e.key === 'Escape') close()
}
onMounted(() => {
  window.addEventListener('blur', onBlur)
  window.addEventListener('resize', onBlur)
  window.addEventListener('keydown', onWindowKey)
})
onBeforeUnmount(() => {
  window.removeEventListener('blur', onBlur)
  window.removeEventListener('resize', onBlur)
  window.removeEventListener('keydown', onWindowKey)
})
</script>

<style scoped>
.cm-layer {
  position: fixed;
  inset: 0;
  z-index: 1000;
}
.cm {
  position: fixed;
  min-width: 220px;
  max-width: 320px;
  max-height: min(72vh, 560px);
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 4px;
  outline: none;
  animation: cm-in 0.12s var(--ease-out);
}
@keyframes cm-in {
  from {
    opacity: 0;
    transform: translateY(-3px) scale(0.98);
  }
}
.cm-item {
  display: flex;
  width: 100%;
  height: 32px;
  align-items: center;
  gap: 10px;
  padding: 0 10px;
  border-radius: 5px;
  font-size: 13px;
  text-align: left;
  color: rgb(var(--c-fg) / 0.92);
}
.cm-item.is-active {
  background: rgb(var(--c-tint) / 0.08);
  color: rgb(var(--c-fg));
}
.cm-item:disabled {
  opacity: 0.4;
}
.cm-item.is-danger {
  color: rgb(var(--c-danger));
}
.cm-item.is-danger.is-active {
  background: rgb(var(--c-danger) / 0.12);
}
.cm-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  opacity: 0.85;
}
.cm-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cm-shortcut {
  font-size: 12px;
  color: rgb(var(--c-fg) / var(--fg-45));
}
.cm-check {
  width: 14px;
  height: 14px;
  color: rgb(var(--c-accent));
}
.cm-sep {
  height: 1px;
  margin: 4px 6px;
  background: rgb(var(--c-tint) / 0.1);
}
.cm-header {
  padding: 6px 10px 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgb(var(--c-fg) / var(--fg-45));
}
</style>
