<template>
  <transition name="bar">
    <div
      v-if="ui.lyricsSyncOpen.value"
      class="offset-card"
      role="group"
      :aria-label="t('lyrics.sync')"
      @keydown.esc.stop.prevent="ui.lyricsSyncOpen.value = false"
    >
      <!-- The quick way first: the line being heard, clicked, and the words
           line up to it. Working out "early or late, and by how much" by ear
           is the hard way, kept below for the last tenth of a second. -->
      <div class="oc-head">
        <span class="oc-icon"><Icon icon="ph:hand-pointing-bold" class="h-4 w-4" /></span>
        <div class="min-w-0 flex-1">
          <p class="oc-title">{{ t('lyrics.syncTap') }}</p>
          <p class="oc-sub">{{ t('lyrics.syncTapSub') }}</p>
        </div>
        <button
          class="icon-btn is-round press h-7 w-7 shrink-0"
          :title="t('common.close')"
          :aria-label="t('common.close')"
          @click="ui.lyricsSyncOpen.value = false"
        >
          <Icon icon="ph:x-bold" class="h-3.5 w-3.5" />
        </button>
      </div>

      <div class="oc-row">
        <button class="oc-step press" :title="t('lyrics.syncEarlier')" :aria-label="t('lyrics.syncEarlier')" @click="tools.nudge(-0.1)">
          <Icon icon="ph:caret-left-bold" class="h-3.5 w-3.5" />
          {{ t('lyrics.syncEarlierShort') }}
        </button>
        <span class="oc-val" :class="{ zero: tools.offset.value === 0 }" aria-live="polite">
          {{ tools.offset.value > 0 ? '+' : '' }}{{ tools.offset.value.toFixed(1) }}s
        </span>
        <button class="oc-step press" :title="t('lyrics.syncLater')" :aria-label="t('lyrics.syncLater')" @click="tools.nudge(0.1)">
          {{ t('lyrics.syncLaterShort') }}
          <Icon icon="ph:caret-right-bold" class="h-3.5 w-3.5" />
        </button>
        <button
          class="icon-btn is-round press h-7 w-7"
          :title="t('lyrics.syncReset')"
          :aria-label="t('lyrics.syncReset')"
          :disabled="tools.offset.value === 0"
          @click="tools.resetOffset()"
        >
          <Icon icon="ph:arrow-counter-clockwise" class="h-3.5 w-3.5" />
        </button>
        <span class="oc-kept" :class="{ on: tools.saved.value }" aria-live="polite">
          <Icon icon="ph:check-bold" class="h-3 w-3" />
          {{ t('lyrics.syncKept') }}
        </span>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { Icon } from '@iconify/vue'
import { useUi } from '/src/model/ui'
import { useI18n } from '/src/i18n'
import { useLyricsTools } from '/src/model/lyrics/useLyricsTools'

// Lining this song's words up with it as it plays, kept by itself.
const { t } = useI18n()
const ui = useUi()
const tools = useLyricsTools()
</script>

<style scoped>
/* A dark floating surface in every theme, like the toasts: it sits over
   the lyrics, and over the cover art in Now Playing, where the theme's own
   surfaces lose their contrast. */
.offset-card {
  --c-fg: 255 255 255;
  --c-tint: 255 255 255;
  position: absolute;
  bottom: 0.75rem;
  left: 50%;
  z-index: 7;
  display: flex;
  width: min(380px, calc(100% - 1rem));
  flex-direction: column;
  gap: 10px;
  padding: 12px 12px 10px 14px;
  border-radius: 16px;
  border: 1px solid rgb(255 255 255 / 0.1);
  background: rgb(36 37 42 / 0.95);
  box-shadow: var(--shadow-pop);
  backdrop-filter: blur(12px);
  color: rgb(var(--c-fg));
  transform: translateX(-50%);
}
.oc-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.oc-icon {
  display: grid;
  width: 28px;
  height: 28px;
  flex: none;
  place-items: center;
  border-radius: 9px;
  background: rgb(var(--c-accent) / 0.18);
  color: rgb(var(--c-accent));
}
.oc-title {
  font-size: 13px;
  font-weight: 700;
  line-height: 1.3;
}
.oc-sub {
  margin-top: 2px;
  font-size: 11.5px;
  line-height: 1.4;
  color: rgb(var(--c-fg) / 0.6);
}
.oc-row {
  display: flex;
  align-items: center;
  gap: 4px;
}
.oc-step {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgb(255 255 255 / 0.08);
  font-size: 12px;
  font-weight: 600;
  transition: background-color 0.12s ease;
}
.oc-step:hover {
  background: rgb(255 255 255 / 0.14);
}
.oc-val {
  min-width: 3.2rem;
  text-align: center;
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--c-accent));
}
.oc-val.zero {
  color: rgb(var(--c-fg) / 0.55);
}
.oc-kept {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  font-size: 11.5px;
  color: rgb(var(--c-accent));
  opacity: 0;
  transition: opacity 0.2s ease;
}
.oc-kept.on {
  opacity: 1;
}
/* Narrow panes keep the controls and lose the explanation first. */
@container lyricsbar (max-width: 340px) {
  .oc-sub,
  .oc-kept {
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
