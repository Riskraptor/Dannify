<template>
  <Teleport to="body">
    <transition name="dlg">
      <div v-if="ui.shortcutsOpen.value" class="sc-layer" @mousedown.self="close">
        <div
          ref="box"
          v-overlay-scroll
          class="sc menu-surface"
          role="dialog"
          aria-modal="true"
          :aria-label="t('shortcuts.title')"
          tabindex="-1"
          @keydown.stop="onKey"
        >
          <header class="flex items-center justify-between px-5 pb-2 pt-4">
            <h2 class="text-[15px] font-semibold">{{ t('shortcuts.title') }}</h2>
            <button class="icon-btn" :title="t('common.close')" @click="close">
              <Icon icon="ph:x" class="h-4 w-4" />
            </button>
          </header>
          <div class="grid gap-x-8 gap-y-5 px-5 pb-5 pt-2 sm:grid-cols-2">
            <section v-for="group in groups" :key="group.title">
              <p class="eyebrow mb-2">{{ group.title }}</p>
              <div v-for="row in group.rows" :key="row.label" class="sc-row">
                <span class="text-[13px] text-fg/80">{{ row.label }}</span>
                <span class="flex gap-1">
                  <kbd v-for="k in row.keys" :key="k" class="kbd">{{ k }}</kbd>
                </span>
              </div>
            </section>
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { computed, ref, watch, nextTick } from 'vue'
import { Icon } from '@iconify/vue'
import { useUi } from '/src/model/ui'
import { desktop } from '/src/desktop/bridge'
import { useI18n } from '/src/i18n'
import { rememberFocus, trapTab } from '/src/model/focusTrap'

const { t } = useI18n()
const ui = useUi()
const box = ref(null)

let giveBack = null

function close() {
  ui.shortcutsOpen.value = false
}
function onKey(e) {
  if (e.key === 'Escape') {
    e.preventDefault()
    close()
    return
  }
  trapTab(e, box.value)
}
watch(
  () => ui.shortcutsOpen.value,
  async (open) => {
    if (!open) {
      const back = giveBack
      giveBack = null
      back?.()
      return
    }
    giveBack = rememberFocus()
    await nextTick()
    box.value && box.value.focus()
  }
)

const groups = computed(() => [
  {
    title: t('shortcuts.playback'),
    rows: [
      { label: t('shortcuts.playPause'), keys: ['Space'] },
      { label: t('shortcuts.nextPrev'), keys: ['N', 'P'] },
      { label: t('shortcuts.nextPrev'), keys: ['Shift', '←/→'] },
      { label: t('shortcuts.seek'), keys: ['←', '→'] },
      { label: t('shortcuts.volume'), keys: ['↑', '↓'] },
      { label: t('shortcuts.mute'), keys: ['M'] },
      { label: t('shortcuts.shuffleRepeat'), keys: ['S', 'R'] },
    ],
  },
  {
    title: t('shortcuts.navigation'),
    rows: [
      { label: t('shortcuts.search'), keys: ['Ctrl', 'K / F'] },
      { label: t('shortcuts.backForward'), keys: ['Alt', '←/→'] },
      { label: t('shortcuts.settings'), keys: ['Ctrl', ','] },
      { label: t('shortcuts.sidebar'), keys: ['Ctrl', 'B'] },
      { label: t('shortcuts.lyrics'), keys: ['Ctrl', 'L'] },
      { label: t('shortcuts.queue'), keys: ['Ctrl', 'Q'] },
      { label: t('shortcuts.nowPlaying'), keys: ['Ctrl', 'E'] },
    ],
  },
  {
    title: t('shortcuts.lists'),
    rows: [
      { label: t('shortcuts.playSelected'), keys: ['Enter'] },
      { label: t('shortcuts.multiSelect'), keys: ['Ctrl/Shift', 'Click'] },
      { label: t('shortcuts.selectAll'), keys: ['Ctrl', 'A'] },
      { label: t('shortcuts.deleteSelected'), keys: ['Del'] },
      { label: t('shortcuts.contextMenu'), keys: ['Shift', 'F10'] },
    ],
  },
  ...(desktop.isDesktop
    ? [
        {
          title: t('shortcuts.window'),
          rows: [
            { label: t('shortcuts.miniPlayer'), keys: ['Ctrl', 'Shift', 'M'] },
            { label: t('shortcuts.fullscreen'), keys: ['F11'] },
            { label: t('shortcuts.refresh'), keys: ['F5'] },
            { label: t('shortcuts.help'), keys: ['Ctrl', '/'] },
          ],
        },
      ]
    : []),
  // Shortcuts that work in any app, when they are turned on in Settings.
  ...(desktop.isDesktop && desktop.state.globalHotkeys
    ? [
        {
          title: t('shortcuts.everywhere'),
          rows: [
            { label: t('shortcuts.playPause'), keys: ['Ctrl', 'Alt', 'P'] },
            { label: t('shortcuts.nextPrev'), keys: ['Ctrl', 'Alt', '←/→'] },
          ],
        },
      ]
    : []),
])
</script>

<style scoped>
.sc-layer {
  position: fixed;
  inset: 0;
  z-index: 1100;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgb(0 0 0 / 0.45);
}
.sc {
  width: min(720px, 100%);
  max-height: calc(100vh - 48px);
  overflow: auto;
  outline: none;
}
.sc-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  height: 30px;
}
.dlg-enter-active,
.dlg-leave-active {
  transition: opacity 0.14s ease;
}
.dlg-enter-from,
.dlg-leave-to {
  opacity: 0;
}
</style>
