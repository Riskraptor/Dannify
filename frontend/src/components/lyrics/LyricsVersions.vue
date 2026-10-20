<template>
  <transition name="bar">
    <div
      v-if="tools.versionsOpen.value"
      class="versions-card"
      role="dialog"
      :aria-label="t('lyrics.versionsTitle')"
      @keydown.esc.stop.prevent="tools.versionsOpen.value = false"
    >
      <div class="vc-head">
        <div class="min-w-0 flex-1">
          <p class="vc-title">{{ t('lyrics.versionsTitle') }}</p>
          <p class="vc-sub">{{ t('lyrics.versionsHint') }}</p>
        </div>
        <button
          class="icon-btn is-round press h-7 w-7 shrink-0"
          :title="t('common.close')"
          :aria-label="t('common.close')"
          @click="tools.versionsOpen.value = false"
        >
          <Icon icon="ph:x-bold" class="h-3.5 w-3.5" />
        </button>
      </div>

      <div v-if="tools.versionsLoading.value" class="vc-loading"><span class="spinner h-5 w-5" /></div>
      <!-- Each version said for what it is, so the choice is not a blind
           "next": how it is timed, its length beside the song's, its size,
           and how it starts. Picking one keeps it for this song. -->
      <ul v-else class="vc-list" role="listbox" :aria-label="t('lyrics.versionsTitle')">
        <li v-for="v in tools.versions.value" :key="v.index">
          <button
            class="vc-item press"
            :class="{ 'is-on': v.index === current }"
            role="option"
            :aria-selected="v.index === current ? 'true' : 'false'"
            :disabled="tools.switching.value"
            @click="tools.chooseVersion(v.index)"
          >
            <span class="vc-radio" aria-hidden="true" />
            <span class="min-w-0 flex-1">
              <span class="vc-name">
                {{ t('lyrics.versionName', { n: v.index + 1 }) }}
                <span v-if="v.index === 0" class="vc-best">{{ t('lyrics.versionBest') }}</span>
              </span>
              <span class="vc-meta">{{ meta(v.about) }}</span>
              <span v-if="v.preview.length" class="vc-preview" dir="auto">{{ v.preview.join(' / ') }}</span>
            </span>
          </button>
        </li>
      </ul>
    </div>
  </transition>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { usePlayer } from '/src/model/player'
import { useLyricsTools } from '/src/model/lyrics/useLyricsTools'

const { t } = useI18n()
const player = usePlayer()
const tools = useLyricsTools()
const current = computed(() => player.lyricVersionIndex.value || 0)

function clock(seconds) {
  const s = Math.round(seconds)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

function meta(about = {}) {
  const parts = [about.words ? t('lyrics.versionWords') : t('lyrics.versionLines')]
  if (typeof about.diff === 'number') {
    const d = Math.abs(about.diff)
    const fit =
      d <= 2
        ? t('lyrics.versionSame')
        : about.diff > 0
          ? t('lyrics.versionLonger', { count: d })
          : t('lyrics.versionShorter', { count: d })
    parts.push(about.length ? `${clock(about.length)} · ${fit}` : fit)
  } else if (about.length) {
    parts.push(clock(about.length))
  }
  if (about.lines) parts.push(t('lyrics.versionLineCount', { count: about.lines }))
  return parts.join(' · ')
}
</script>

<style scoped>
.versions-card {
  --c-fg: 255 255 255;
  --c-tint: 255 255 255;
  position: absolute;
  bottom: 0.75rem;
  left: 50%;
  z-index: 8;
  display: flex;
  width: min(400px, calc(100% - 1rem));
  max-height: calc(100% - 1.5rem);
  flex-direction: column;
  gap: 8px;
  padding: 12px 8px 8px 14px;
  border-radius: 16px;
  border: 1px solid rgb(255 255 255 / 0.1);
  background: rgb(36 37 42 / 0.96);
  box-shadow: var(--shadow-pop);
  backdrop-filter: blur(12px);
  color: rgb(var(--c-fg));
  transform: translateX(-50%);
}
.vc-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding-right: 4px;
}
.vc-title {
  font-size: 13px;
  font-weight: 700;
}
.vc-sub {
  margin-top: 2px;
  font-size: 11.5px;
  color: rgb(var(--c-fg) / 0.6);
}
.vc-loading {
  display: grid;
  place-items: center;
  padding: 18px 0;
  color: rgb(var(--c-fg) / 0.7);
}
.vc-list {
  display: flex;
  min-height: 0;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
  padding-right: 4px;
}
.vc-item {
  display: flex;
  width: 100%;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 10px 8px 6px;
  border-radius: 10px;
  text-align: left;
  transition: background-color 0.12s ease;
}
.vc-item:hover {
  background: rgb(255 255 255 / 0.07);
}
.vc-item.is-on {
  background: rgb(var(--c-accent) / 0.14);
}
.vc-radio {
  width: 14px;
  height: 14px;
  flex: none;
  margin-top: 2px;
  border-radius: 50%;
  border: 2px solid rgb(var(--c-fg) / 0.4);
}
.vc-item.is-on .vc-radio {
  border: 4px solid rgb(var(--c-accent));
}
.vc-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
}
.vc-best {
  padding: 1px 7px;
  border-radius: 999px;
  background: rgb(var(--c-accent) / 0.18);
  font-size: 10.5px;
  font-weight: 700;
  color: rgb(var(--c-accent));
}
.vc-meta,
.vc-preview {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.vc-meta {
  margin-top: 2px;
  font-size: 11.5px;
  color: rgb(var(--c-fg) / 0.65);
}
.vc-preview {
  margin-top: 2px;
  font-size: 11.5px;
  font-style: italic;
  color: rgb(var(--c-fg) / 0.45);
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
