<template>
  <div class="lt" :class="{ 'is-bar': bar }" role="toolbar" :aria-label="t('lyrics.title')">
    <!-- Nudge the timing of this song's lyrics. Shown, disabled, before the
         lyrics are in, so the bar does not shuffle when they arrive. -->
    <button
      class="lt-btn press"
      :class="{ 'is-active': ui.lyricsSyncOpen.value, 'is-tuned': tools.offset.value !== 0 }"
      :title="t('lyrics.syncHint')"
      :aria-label="t('lyrics.syncHint')"
      :aria-pressed="ui.lyricsSyncOpen.value ? 'true' : 'false'"
      :disabled="!tools.hasLines.value"
      @click="ui.lyricsSyncOpen.value = !ui.lyricsSyncOpen.value"
    >
      <Icon icon="ph:sliders-horizontal" class="h-4 w-4" />
      <span v-if="bar" class="lt-label">
        {{ tools.offset.value === 0 ? t('lyrics.sync') : `${tools.offset.value > 0 ? '+' : ''}${tools.offset.value.toFixed(1)}s` }}
      </span>
    </button>

    <!-- Fetch again, past every cache -->
    <button
      class="lt-btn press"
      :disabled="tools.refreshing.value"
      :title="t('lyrics.refresh')"
      :aria-label="t('lyrics.refresh')"
      @click="tools.refresh"
    >
      <Icon icon="ph:arrows-clockwise" class="h-4 w-4" :class="{ 'animate-spin': tools.refreshing.value }" />
      <span v-if="bar" class="lt-label">{{ t('common.refresh') }}</span>
    </button>

    <!-- Which version is showing (only when there are several). Last of
         the group: it appears once the lyrics are in, and that way nothing
         else moves when it does. -->
    <button
      v-if="tools.hasVersions.value"
      class="lt-btn press"
      :title="t('lyrics.versionHint')"
      :aria-label="versionLabel"
      :disabled="tools.switching.value"
      @click="tools.switchVersion"
    >
      <Icon icon="ph:stack" class="h-4 w-4" />
      <!-- Both are rendered; which one shows is down to how much room the
           bar has. See the container queries at the foot of this file. -->
      <span v-if="bar" class="lt-label">{{ versionLabel }}</span>
      <span v-if="tools.versionsCounted.value" class="lt-badge" :class="{ 'is-fallback': bar }">
        {{ tools.versionIndex.value }}
      </span>
    </button>

    <span v-if="bar" class="lt-spring" />

    <!-- Contribute: the whole point of the lyrics feature, so it is a real,
         labelled button rather than one more anonymous icon. -->
    <button
      v-if="tools.hasTrack.value"
      class="lt-contribute press"
      :class="{ 'is-primary': !tools.hasLines.value && !tools.loading.value }"
      :title="t('lyrics.contributeHint')"
      :aria-label="tools.hasLines.value ? t('lyrics.improve') : t('lyrics.contribute')"
      @click="tools.contribute"
    >
      <Icon :icon="tools.hasLines.value ? 'ph:pencil-simple' : 'ph:plus-bold'" class="h-4 w-4" />
      <span v-if="bar" class="lt-label">
        {{ tools.hasLines.value ? t('lyrics.improve') : t('lyrics.contribute') }}
      </span>
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import { useUi } from '/src/model/ui'
import { useI18n } from '/src/i18n'
import { useLyricsTools } from '/src/model/lyrics/useLyricsTools'

// `bar` renders the labelled toolbar at the foot of the lyrics panel;
// without it the same actions collapse to icons for tight headers.
defineProps({ bar: { type: Boolean, default: false } })

const { t } = useI18n()
const ui = useUi()
const tools = useLyricsTools()

const versionLabel = computed(() =>
  tools.versionsCounted.value
    ? t('lyrics.versionOf', { n: tools.versionIndex.value, total: tools.versionTotal.value })
    : t('lyrics.otherVersions')
)
</script>

<style scoped>
.lt {
  display: flex;
  align-items: center;
  gap: 2px;
}
.lt.is-bar {
  gap: 4px;
  min-height: 38px;
  padding: 6px 4px 2px;
  border-top: 1px solid rgb(var(--c-tint) / 0.07);
  /* A last line of defence: even if a translation runs long, the bar folds
     instead of running out of the panel. */
  flex-wrap: wrap;
}
.lt-badge.is-fallback {
  display: none;
}
.lt-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 8px;
  border-radius: 6px;
  color: rgb(var(--c-fg) / 0.62);
  transition:
    background-color 0.12s ease,
    color 0.12s ease;
}
.lt-btn:hover:not(:disabled) {
  background: rgb(var(--c-tint) / 0.09);
  color: rgb(var(--c-fg));
}
.lt-btn:disabled {
  opacity: 0.45;
}
.lt-btn.is-active {
  background: rgb(var(--c-tint) / 0.1);
  color: rgb(var(--c-fg));
}
.lt-btn.is-tuned {
  color: rgb(var(--c-accent));
}
.lt-label {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
.lt-badge {
  font-size: 11px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--c-accent));
}
.lt-spring {
  flex: 1;
}
.lt-contribute {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.75);
  background: rgb(var(--c-tint) / 0.09);
  transition:
    background-color 0.12s ease,
    color 0.12s ease;
}
.lt-contribute:hover {
  background: rgb(var(--c-tint) / 0.15);
  color: rgb(var(--c-fg));
}
.lt-contribute.is-primary {
  background: rgb(var(--c-accent));
  color: rgb(var(--c-accent-fg));
}
.lt-contribute.is-primary:hover {
  filter: brightness(1.06);
}
/* The labelled bar only fits while the panel is wide. The panel can be
   dragged down to 300 px and the window itself to 760, at which point four
   labelled buttons are half again wider than the space they have. Below
   each threshold the text drops and the icons carry the meaning.

   Both hosts declare the container: see .spanel and .np-right. */
@container lyricsbar (max-width: 470px) {
  .lt.is-bar .lt-label {
    display: none;
  }
  .lt.is-bar .lt-badge.is-fallback {
    display: inline;
  }
  .lt.is-bar {
    gap: 2px;
  }
}
@container lyricsbar (max-width: 330px) {
  .lt.is-bar .lt-contribute {
    padding: 0 8px;
  }
}
</style>
