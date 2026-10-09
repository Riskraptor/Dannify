<template>
  <Teleport to="body">
    <transition name="ed-modal">
      <!-- Closing on a press that starts on the backdrop, not on a click: a
           text selection dragged out of the editor ended over the backdrop
           and closed it. -->
      <div v-if="open" class="ed-backdrop" @mousedown.self="close">
        <div
          ref="shell"
          class="ed-shell"
          role="dialog"
          aria-modal="true"
          aria-labelledby="ed-title"
          tabindex="-1"
        >
          <header class="ed-head">
            <CoverImage :src="s.cover.value" radius="sm" :size="44" class="ed-art" />
            <div class="ed-titles">
              <p class="ed-eyebrow">{{ t('publish.contributeTo') }}</p>
              <h2 id="ed-title" class="ed-title" dir="auto">{{ s.song.value.title || s.form.value.track || '—' }}</h2>
              <p class="ed-by" dir="auto">{{ s.song.value.artist || s.form.value.artist }}</p>
            </div>
            <button
              class="icon-btn is-round press"
              :title="t('common.close')"
              :aria-label="t('common.close')"
              :disabled="s.status.value === 'sending'"
              @click="close"
            >
              <Icon icon="ph:x-bold" class="h-4 w-4" />
            </button>
          </header>

          <EditorStepper />

          <StepWords v-if="s.phase.value === WORDS" />
          <StepSync v-else-if="s.phase.value === SYNC" />
          <StepReview v-else />
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, provide, onBeforeUnmount } from 'vue'
import { Icon } from '@iconify/vue'
import { usePlayer } from '/src/model/player'
import { useI18n } from '/src/i18n'
import { useDialogs } from '/src/model/dialog'
import { rememberFocus, trapTab } from '/src/model/focusTrap'
import { useLyricsSubmit, LYRICS_EDITOR, WORDS, SYNC } from '/src/model/lyrics/useLyricsSubmit'
import { useSyncSession } from '/src/model/lyrics/useSyncSession'
import CoverImage from '/src/components/ui/CoverImage.vue'
import EditorStepper from './editor/EditorStepper.vue'
import StepWords from './editor/StepWords.vue'
import StepSync from './editor/StepSync.vue'
import StepReview from './editor/StepReview.vue'

// The lyrics editor: write the words, tap along to time them, check and
// publish. App.vue keeps the one instance; everything else opens it with
// the `dannify:open-lyrics-submit` event.

const props = defineProps({ open: { type: Boolean, default: false } })
const emit = defineEmits(['close'])

const { t } = useI18n()
const player = usePlayer()
const { queue: dialogQueue } = useDialogs()

const shell = ref(null)
const s = useLyricsSubmit({ player })
const session = useSyncSession({
  player,
  editor: s.editor,
  enabled: computed(() => props.open && s.phase.value === SYNC),
  // Off the button, but still inside the editor, so Tab carries on from here.
  release: () => shell.value?.querySelector('[data-sync-home]')?.focus({ preventScroll: true }),
})

provide(LYRICS_EDITOR, { s, session, player, close })

let giveBack = null

function close() {
  // Publishing cannot be called back once it has started.
  if (s.status.value === 'sending') return
  emit('close')
}

// In every step: Escape closes (the line being typed in takes it first, and
// so does a dialog on top), and Tab stays inside the editor.
function onKey(e) {
  if (dialogQueue.value.length) return
  if (e.key === 'Escape') {
    if (s.editor.editing.value !== -1) return
    e.preventDefault()
    e.stopPropagation()
    close()
    return
  }
  if (e.key === 'Tab') {
    trapTab(e, shell.value)
    return
  }
  session.handleKey(e)
}

// Window-level and capturing, so the editor's keys work wherever the focus
// is inside it, ahead of the app's own shortcuts.
function bindKeys(on) {
  if (typeof window === 'undefined') return
  window.removeEventListener('keydown', onKey, true)
  if (on) window.addEventListener('keydown', onKey, true)
}

function leave() {
  session.stopLoop()
  // Slow motion is for timing. Every way out puts the listener's own speed
  // back, or every song after it played at half speed until a restart.
  player.restoreSpeed()
  player.noAutoAdvance.value = false
  s.close()
  bindKeys(false)
}

watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) {
      leave()
      const back = giveBack
      giveBack = null
      back?.()
      return
    }
    giveBack = rememberFocus()
    // While the editor is open the song must not move on to the next one at
    // its end: that would pull the words being timed out from under the user.
    player.noAutoAdvance.value = true
    bindKeys(true)
    s.open()
  }
)

onBeforeUnmount(leave)
</script>

<style scoped>
/* The editor borrows the app's own tokens so it reads as part of Dannify
   rather than a web form that happens to be on top of it. */
.ed-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgb(0 0 0 / 0.55);
  backdrop-filter: blur(10px) saturate(0.9);
}
[data-mode='light'] .ed-backdrop {
  background: rgb(210 214 222 / 0.7);
}
/* A fixed size whatever the step: moving between steps never resizes the
   window under the pointer. */
.ed-shell {
  container: editor / inline-size;
  display: flex;
  flex-direction: column;
  width: min(1000px, 100%);
  height: min(800px, 100%);
  overflow: hidden;
  border-radius: 14px;
  border: 1px solid rgb(var(--c-tint) / 0.1);
  background: rgb(var(--c-elev));
  color: rgb(var(--c-fg));
  box-shadow: var(--shadow-pop);
  outline: none;
}
.ed-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 14px 10px 18px;
}
.ed-art {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  box-shadow: 0 4px 14px rgb(0 0 0 / 0.25);
}
.ed-titles {
  min-width: 0;
  flex: 1;
}
.ed-eyebrow {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: rgb(var(--c-accent));
}
.ed-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 1.3;
}
.ed-by {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12.5px;
  color: rgb(var(--c-fg) / 0.55);
}
.ed-head .icon-btn {
  align-self: flex-start;
}
@media (max-width: 640px), (max-height: 520px) {
  .ed-backdrop {
    padding: 0;
  }
  .ed-shell {
    width: 100%;
    height: 100%;
    border-radius: 0;
    border: 0;
  }
}
.ed-modal-enter-active,
.ed-modal-leave-active {
  transition: opacity 0.18s ease;
}
.ed-modal-enter-active .ed-shell,
.ed-modal-leave-active .ed-shell {
  transition: transform 0.22s var(--ease-out);
}
.ed-modal-enter-from,
.ed-modal-leave-to {
  opacity: 0;
}
.ed-modal-enter-from .ed-shell,
.ed-modal-leave-to .ed-shell {
  transform: translateY(8px) scale(0.985);
}
@media (prefers-reduced-motion: reduce) {
  .ed-modal-enter-active .ed-shell,
  .ed-modal-leave-active .ed-shell {
    transition: none;
  }
}
</style>
