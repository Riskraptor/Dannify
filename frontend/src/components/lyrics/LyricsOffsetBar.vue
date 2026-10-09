<template>
  <transition name="bar">
    <div
      v-if="ui.lyricsSyncOpen.value"
      class="offset-bar"
      role="group"
      :aria-label="t('lyrics.sync')"
      @keydown.esc.stop.prevent="ui.lyricsSyncOpen.value = false"
    >
      <span class="ob-label">{{ t('lyrics.sync') }}</span>
      <button
        class="icon-btn is-round press h-7 w-7"
        :title="t('lyrics.syncEarlier')"
        :aria-label="t('lyrics.syncEarlier')"
        @click="player.adjustLyricsOffset(-0.2)"
      >
        <Icon icon="ph:minus-bold" class="h-3.5 w-3.5" />
      </button>
      <span class="ob-val" :class="{ zero: tools.offset.value === 0 }" aria-live="polite">
        {{ tools.offset.value > 0 ? '+' : '' }}{{ tools.offset.value.toFixed(1) }}s
      </span>
      <button
        class="icon-btn is-round press h-7 w-7"
        :title="t('lyrics.syncLater')"
        :aria-label="t('lyrics.syncLater')"
        @click="player.adjustLyricsOffset(0.2)"
      >
        <Icon icon="ph:plus-bold" class="h-3.5 w-3.5" />
      </button>
      <button
        class="icon-btn is-round press h-7 w-7"
        :title="t('lyrics.syncReset')"
        :aria-label="t('lyrics.syncReset')"
        :disabled="tools.offset.value === 0"
        @click="player.resetLyricsOffset()"
      >
        <Icon icon="ph:arrow-counter-clockwise" class="h-3.5 w-3.5" />
      </button>
      <button class="btn-accent btn-pill press ob-save" :disabled="tools.saving.value" @click="tools.saveOffset">
        <Icon :icon="tools.saved.value ? 'ph:check-bold' : 'ph:floppy-disk'" class="h-3.5 w-3.5" />
        {{ tools.saved.value ? t('lyrics.syncSaved') : t('lyrics.syncSave') }}
      </button>
      <button
        class="icon-btn is-round press h-7 w-7"
        :title="t('common.close')"
        :aria-label="t('common.close')"
        @click="ui.lyricsSyncOpen.value = false"
      >
        <Icon icon="ph:x-bold" class="h-3.5 w-3.5" />
      </button>
    </div>
  </transition>
</template>

<script setup>
import { Icon } from '@iconify/vue'
import { usePlayer } from '/src/model/player'
import { useUi } from '/src/model/ui'
import { useI18n } from '/src/i18n'
import { useLyricsTools } from '/src/model/lyrics/useLyricsTools'

// Moving this song's words earlier or later as it plays, then keeping it.
const { t } = useI18n()
const player = usePlayer()
const ui = useUi()
const tools = useLyricsTools()
</script>

<style scoped>
/* A dark floating surface in every theme, like the toasts: it sits over
   the lyrics, and over the cover art in Now Playing, where the theme's own
   surfaces lose their contrast. */
.offset-bar {
  --c-fg: 255 255 255;
  --c-tint: 255 255 255;
  color: rgb(var(--c-fg));
  background: rgb(36 37 42 / 0.94);
  border: 1px solid rgb(255 255 255 / 0.1);
  box-shadow: var(--shadow-pop);
  backdrop-filter: blur(12px);
  position: absolute;
  bottom: 0.75rem;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 0.2rem;
  max-width: calc(100% - 1rem);
  padding: 0.3rem 0.35rem 0.3rem 0.8rem;
  border-radius: 9999px;
  z-index: 7;
  white-space: nowrap;
}
.ob-label {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: rgb(var(--c-fg) / 0.5);
  padding-right: 0.2rem;
}
.ob-val {
  min-width: 2.8rem;
  text-align: center;
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--c-accent));
}
.ob-val.zero {
  color: rgb(var(--c-fg) / 0.55);
}
.ob-save {
  height: 1.75rem;
  margin-left: 0.15rem;
  padding: 0 0.75rem;
  font-size: 12px;
}
/* Narrow panes keep the controls and lose the caption first. */
@container lyricsbar (max-width: 340px) {
  .ob-label {
    display: none;
  }
}
.bar-enter-active,
.bar-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}
.bar-enter-from,
.bar-leave-to {
  opacity: 0;
  transform: translate(-50%, 10px);
}
</style>
