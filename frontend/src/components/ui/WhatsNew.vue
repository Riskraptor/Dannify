<template>
  <div class="wn" :class="{ 'is-flat': flat }">
    <!-- Under a welcome that already names the version: the summary alone. -->
    <p v-if="bare && read.summary" class="wn-intro">{{ read.summary }}</p>
    <header v-if="!bare" class="wn-head">
      <span class="wn-badge" aria-hidden="true">
        <Icon icon="ph:sparkle-fill" class="h-5 w-5" />
      </span>
      <div class="min-w-0">
        <h3 class="wn-title">{{ t('update.whatsNewTitle', { version }) }}</h3>
        <p class="wn-summary">{{ read.summary || (!read.highlights.length ? t('update.whatsNewEmpty') : '') }}</p>
      </div>
    </header>

    <ul v-if="read.highlights.length" class="wn-grid">
      <li v-for="(item, i) in read.highlights" :key="i" class="wn-card" :style="{ '--i': i }">
        <span class="wn-icon" aria-hidden="true">
          <Icon :icon="iconFor(item)" class="h-[18px] w-[18px]" />
        </span>
        <div class="min-w-0">
          <p v-if="item.title" class="wn-card-title">{{ item.title }}</p>
          <p v-if="item.text" class="wn-card-text">{{ item.text }}</p>
        </div>
      </li>
    </ul>

    <div v-if="read.fixes.length" class="wn-fixes">
      <p class="wn-sub">{{ t('update.fixedHeading') }}</p>
      <ul>
        <li v-for="(item, i) in read.fixes" :key="i">
          <Icon icon="ph:check-circle-fill" class="wn-check" aria-hidden="true" />
          <span>
            <strong v-if="item.title">{{ item.title }}. </strong>{{ item.text }}
          </span>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import { readNotes } from '/src/model/releaseNotes'
import { useI18n } from '/src/i18n'

// What a new version brings, the way people want to read it: a line that
// says what it is, a card for each thing that is new, and the fixes in a
// short list. Read out of the release's notes (model/releaseNotes.js), which
// are written for the releases page and carry downloads and commands this
// leaves out. Nothing here points anywhere else: what is new is all of it.

const props = defineProps({
  version: { type: String, default: '' },
  notes: { type: String, default: '' },
  // Inside a dialog: no box of its own around it.
  flat: { type: Boolean, default: false },
  // Without its own heading, under one that already says it.
  bare: { type: Boolean, default: false },
})

const { t } = useI18n()
const read = computed(() => readNotes(props.notes))

// A picture for each card, from what it is about. Written out in full:
// the icons are found in the source by name (vite.config.js).
const ICONS = [
  [/settings|preferences/i, 'ph:gear-six'],
  [/special days|christmas|festive|new year/i, 'ph:confetti'],
  [/^your library|library, tidier|\bpin\b/i, 'ph:books'],
  [/made for you|\bmix(es)?\b/i, 'ph:music-notes-plus'],
  [/year in music|recap/i, 'ph:confetti'],
  [/now playing/i, 'ph:play-circle'],
  [/keeps? going|autoplay|never stops/i, 'ph:infinity'],
  [/album/i, 'ph:vinyl-record'],
  [/listenbrainz|scrobbl/i, 'ph:broadcast'],
  [/stat|history|on repeat|rediscover/i, 'ph:chart-bar'],
  [/palette|shortcut|keyboard/i, 'ph:command'],
  [/search|suggest/i, 'ph:magnifying-glass'],
  [/repair|recover|start fresh|rescue/i, 'ph:lifebuoy'],
  [/linux|macos|mac\b|windows|platform|every system/i, 'ph:devices'],
  [/lyric/i, 'ph:microphone-stage'],
  [/playlist|queue/i, 'ph:playlist'],
  [/sound|equali[sz]|loud|audio/i, 'ph:waveform'],
  [/moved|new home|address|github/i, 'ph:house-line'],
  [/download|sav(e|ing)|offline/i, 'ph:download-simple'],
  [/fast|quick|speed/i, 'ph:lightning'],
  [/secur|safe|protect|private/i, 'ph:shield-check'],
  [/theme|look|design|colou?r/i, 'ph:palette'],
]
// The title says what a card is about; its text often mentions other things
// ("your top songs, artists and albums" is about stats, not albums).
function iconFor(item) {
  const hit =
    (item.title && ICONS.find(([pattern]) => pattern.test(item.title))) ||
    ICONS.find(([pattern]) => pattern.test(`${item.title} ${item.text}`))
  return hit ? hit[1] : 'ph:sparkle'
}
</script>

<style scoped>
.wn {
  display: grid;
  gap: 16px;
  /* An address in a title ("github.com/…") has no space to break at. */
  overflow-wrap: anywhere;
  padding: 18px;
  border-radius: 14px;
  border: 1px solid rgb(var(--c-tint) / 0.1);
  background:
    radial-gradient(120% 90% at 0% 0%, rgb(var(--c-accent) / 0.12), transparent 60%),
    rgb(var(--c-tint) / 0.035);
}
.wn.is-flat {
  padding: 0;
  border: 0;
  background: none;
}

.wn-intro {
  margin: -6px auto 4px;
  max-width: 52ch;
  font-size: 14px;
  line-height: 1.5;
  text-align: center;
  color: rgb(var(--c-fg) / var(--fg-70, 0.72));
}
.wn-head {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}
.wn-badge {
  display: grid;
  flex: none;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: rgb(var(--c-accent));
  color: rgb(var(--c-accent-fg));
  box-shadow: 0 6px 18px -6px rgb(var(--c-accent) / 0.7);
}
.wn-title {
  font-size: 1.12rem;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: -0.01em;
  color: rgb(var(--c-fg));
}
.wn-summary {
  margin-top: 3px;
  font-size: 0.9rem;
  line-height: 1.5;
  color: rgb(var(--c-fg) / var(--fg-60));
}
.wn-summary:empty {
  display: none;
}

.wn-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 10px;
}
.wn-card {
  display: flex;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgb(var(--c-tint) / 0.08);
  background: rgb(var(--c-tint) / 0.04);
  animation: wn-in 0.32s cubic-bezier(0.2, 0.7, 0.2, 1) both;
  animation-delay: calc(var(--i) * 45ms);
}
.wn-icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: rgb(var(--c-accent) / 0.14);
  color: rgb(var(--c-accent));
}
.wn-card-title {
  font-size: 0.9rem;
  font-weight: 650;
  line-height: 1.3;
  color: rgb(var(--c-fg));
}
.wn-card-text {
  margin-top: 2px;
  font-size: 0.82rem;
  line-height: 1.45;
  color: rgb(var(--c-fg) / var(--fg-60));
}
.wn-card-title + .wn-card-text {
  margin-top: 3px;
}

.wn-sub {
  margin-bottom: 8px;
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: rgb(var(--c-fg) / var(--fg-50));
}
.wn-fixes ul {
  display: grid;
  gap: 7px;
}
.wn-fixes li {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  font-size: 0.85rem;
  line-height: 1.45;
  color: rgb(var(--c-fg) / 0.78);
}
.wn-fixes strong {
  font-weight: 600;
  color: rgb(var(--c-fg));
}
.wn-check {
  flex: none;
  width: 16px;
  height: 16px;
  margin-top: 2px;
  color: rgb(var(--c-accent));
}

@keyframes wn-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
}
@media (prefers-reduced-motion: reduce) {
  .wn-card {
    animation: none;
  }
}
</style>
