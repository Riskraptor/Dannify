<template>
  <div class="lc" :class="{ 'is-bar': bar }">
    <!-- Which version is showing (only when there are several) -->
    <button
      v-if="hasVersions"
      class="lc-btn press"
      :title="t('lyrics.versionHint')"
      @click="onSwitchVersion"
    >
      <Icon icon="ph:stack" class="h-4 w-4" />
      <span v-if="bar" class="lc-label">
        {{ t('lyrics.versionOf', { n: verIndex, total: verTotal }) }}
      </span>
      <span v-else class="lc-badge">{{ verIndex }}</span>
    </button>

    <!-- Nudge the timing of this song's lyrics -->
    <button
      v-if="hasLines"
      class="lc-btn press"
      :class="{ 'is-active': ui.lyricsSyncOpen.value, 'is-tuned': offset !== 0 }"
      :title="t('lyrics.syncHint')"
      @click="ui.lyricsSyncOpen.value = !ui.lyricsSyncOpen.value"
    >
      <Icon icon="ph:sliders-horizontal" class="h-4 w-4" />
      <span v-if="bar" class="lc-label">
        {{ offset === 0 ? t('lyrics.sync') : `${offset > 0 ? '+' : ''}${offset.toFixed(1)}s` }}
      </span>
    </button>

    <!-- Re-fetch, bypassing every cache -->
    <button class="lc-btn press" :disabled="refreshing" :title="t('lyrics.refresh')" @click="onRefresh">
      <Icon icon="ph:arrows-clockwise" class="h-4 w-4" :class="{ 'animate-spin': refreshing }" />
      <span v-if="bar" class="lc-label">{{ t('common.refresh') }}</span>
    </button>

    <span v-if="bar" class="lc-spring" />

    <!-- Contribute: the whole point of the lyrics feature, so it is a real,
         labelled button rather than one more anonymous icon. -->
    <button
      v-if="canContribute"
      class="lc-contribute press"
      :class="{ 'is-primary': !hasLines }"
      :title="t('lyrics.contributeHint')"
      @click="onContribute"
    >
      <Icon :icon="hasLines ? 'ph:pencil-simple' : 'ph:plus'" class="h-4 w-4" />
      <span v-if="bar" class="lc-label">
        {{ hasLines ? t('lyrics.improve') : t('lyrics.contribute') }}
      </span>
    </button>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Icon } from '@iconify/vue'
import { usePlayer } from '/src/model/player'
import { useUi } from '/src/model/ui'
import { useI18n } from '/src/i18n'

// `bar` renders the labelled toolbar used at the foot of the lyrics panel;
// without it the same actions collapse to icons for tight headers.
defineProps({ bar: { type: Boolean, default: false } })

const { t } = useI18n()
const player = usePlayer()
const ui = useUi()

const refreshing = ref(false)
const switching = ref(false)

// Contributing is meaningful whenever a track is loaded: the store keeps every
// revision, so improving existing lyrics is as valid as adding the first set.
const canContribute = computed(() => !!player.currentTrack.value)
const hasLines = computed(() => player.lyricsLines.value.length > 0)
const offset = computed(() => player.lyricsOffset.value || 0)

const hasVersions = computed(
  () => hasLines.value && (player.lyricVersionCount.value > 1 || player.lyricVersionCount.value < 0)
)
const verIndex = computed(() => (player.lyricVersionIndex.value || 0) + 1)
const verTotal = computed(() => Math.max(verIndex.value, player.lyricVersionCount.value || 1))

async function onRefresh() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    await player.refreshLyrics()
  } finally {
    refreshing.value = false
  }
}

async function onSwitchVersion() {
  if (switching.value) return
  switching.value = true
  try {
    await player.switchLyricVersion(1)
  } finally {
    switching.value = false
  }
}

// App.vue owns the single publish modal instance; a window event keeps every
// entry point (panel, Now Playing, empty state) decoupled from it.
function onContribute() {
  window.dispatchEvent(new CustomEvent('dannify:open-lyrics-submit'))
}
</script>

<style scoped>
.lc {
  display: flex;
  align-items: center;
  gap: 2px;
}
.lc.is-bar {
  gap: 4px;
  padding: 6px 4px 2px;
  border-top: 1px solid rgb(var(--c-tint) / 0.07);
}
.lc-btn {
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
.lc-btn:hover:not(:disabled) {
  background: rgb(var(--c-tint) / 0.09);
  color: rgb(var(--c-fg));
}
.lc-btn:disabled {
  opacity: 0.5;
}
.lc-btn.is-active {
  background: rgb(var(--c-tint) / 0.1);
  color: rgb(var(--c-fg));
}
.lc-btn.is-tuned {
  color: rgb(var(--c-accent));
}
.lc-label {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
.lc-badge {
  font-size: 11px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--c-accent));
}
.lc-spring {
  flex: 1;
}
.lc-contribute {
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
.lc-contribute:hover {
  background: rgb(var(--c-tint) / 0.15);
  color: rgb(var(--c-fg));
}
.lc-contribute.is-primary {
  background: rgb(var(--c-accent));
  color: rgb(var(--c-accent-fg));
}
.lc-contribute.is-primary:hover {
  filter: brightness(1.06);
}
</style>
