<template>
  <div class="lyrics-empty" :class="{ 'is-compact': compact }">
    <!-- Offline, "none found" would be a guess: say what is actually wrong.
         They come in by themselves when the connection is back. -->
    <template v-if="tools.isOffline.value">
      <span class="le-icon"><Icon icon="ph:wifi-slash" class="h-6 w-6" /></span>
      <p class="le-title">{{ t('lyrics.offlineTitle') }}</p>
      <p v-if="!compact" class="le-text">{{ t('lyrics.offlineText') }}</p>
      <button
        class="btn btn-pill press mt-1"
        :disabled="tools.refreshing.value || tools.checking.value"
        @click="tools.refresh"
      >
        <Icon icon="ph:arrows-clockwise" class="h-4 w-4" :class="{ 'animate-spin': tools.refreshing.value }" />
        {{ t('lyrics.tryAgain') }}
      </button>
    </template>

    <!-- The mini player: a line, and a way to the full window, where there
         is room to write them. -->
    <template v-else-if="compact">
      <span class="le-icon"><Icon icon="ph:microphone-stage" class="h-6 w-6" /></span>
      <p class="le-title">{{ t('lyrics.none') }}</p>
      <button class="le-link" @click="tools.contribute">
        {{ t('lyrics.addInFullWindow') }}
        <Icon icon="ph:arrow-square-out" class="h-3.5 w-3.5" />
      </button>
    </template>

    <!-- Nothing found: writing them is the headline action. -->
    <template v-else>
      <span class="le-icon"><Icon icon="ph:microphone-stage" class="h-6 w-6" /></span>
      <p class="le-title">{{ t('lyrics.none') }}</p>
      <p class="le-text">{{ t('lyrics.contributeBlurb') }}</p>
      <div class="le-actions">
        <button class="btn btn-pill press" :disabled="tools.refreshing.value" @click="tools.refresh">
          <Icon icon="ph:arrows-clockwise" class="h-4 w-4" :class="{ 'animate-spin': tools.refreshing.value }" />
          {{ t('lyrics.tryAgain') }}
        </button>
        <button class="btn-accent btn-pill press" @click="tools.contribute">
          <Icon icon="ph:plus-bold" class="h-4 w-4" />
          {{ t('lyrics.contribute') }}
        </button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { useLyricsTools } from '/src/model/lyrics/useLyricsTools'

defineProps({ compact: { type: Boolean, default: false } })

const { t } = useI18n()
const tools = useLyricsTools()
</script>

<style scoped>
/* The app's empty state (EmptyState.vue), sized for a pane that can be
   short: centred, and scrolling rather than clipping when it has to. */
.lyrics-empty {
  display: flex;
  height: 100%;
  flex-direction: column;
  align-items: center;
  /* "safe": a pane too short for it scrolls from the top instead of
     cutting the icon off above the fold. */
  justify-content: safe center;
  gap: 8px;
  padding: 24px;
  overflow-y: auto;
  text-align: center;
}
.le-icon {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  margin-bottom: 6px;
  flex-shrink: 0;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.06);
  color: rgb(var(--c-fg) / 0.45);
}
.le-title {
  font-size: 15px;
  font-weight: 700;
  color: rgb(var(--c-fg) / 0.9);
}
.le-text {
  max-width: 320px;
  font-size: 12.5px;
  line-height: 1.55;
  color: rgb(var(--c-fg) / 0.55);
}
.le-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 8px;
}
.le-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border-radius: 6px;
  font-size: 12.5px;
  font-weight: 600;
  color: rgb(var(--c-accent));
}
.le-link:hover {
  text-decoration: underline;
}
.is-compact {
  gap: 6px;
  padding: 16px;
}
.is-compact .le-icon {
  width: 44px;
  height: 44px;
  margin-bottom: 2px;
}
.is-compact .le-title {
  font-size: 13px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.65);
}
</style>
