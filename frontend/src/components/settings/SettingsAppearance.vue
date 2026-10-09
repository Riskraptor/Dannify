<template>
  <section>
    <h2 class="group-title">{{ t('settings.appearance') }}</h2>
    <div class="row">
      <Icon icon="ph:palette" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.theme') }}</p>
        <p class="row-hint">{{ tp('settings.themeHint') }}</p>
      </div>
      <div class="seg">
        <button
          v-for="opt in themeOptions"
          :key="opt.value"
          class="seg-item"
          :class="{ 'is-active': theme.preference.value === opt.value }"
          @click="restyle(() => theme.setPreference(opt.value), $event.currentTarget)"
        >
          <Icon :icon="opt.icon" class="h-4 w-4" />
          {{ t(opt.label) }}
        </button>
      </div>
    </div>
    <!-- Interface size. This was Ctrl with plus and minus, and Ctrl with
         the scroll wheel, which is how a browser behaves and made the app
         feel like a page rather than a program. It is a choice you make
         once, here. -->
    <div class="row">
      <Icon icon="ph:text-aa" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.uiScale') }}</p>
        <p class="row-hint">{{ t('settings.uiScaleHint') }}</p>
      </div>
      <div class="seg" role="radiogroup" :aria-label="t('settings.uiScale')">
        <button
          v-for="step in zoomSteps"
          :key="step.value"
          class="seg-item"
          role="radio"
          :aria-checked="zoom === step.value"
          :class="{ 'is-active': zoom === step.value }"
          :title="`${Math.round(step.value * 100)}%`"
          @click="pickZoom(step.value, $event.currentTarget)"
        >
          <span class="zoom-glyph" :style="{ fontSize: `${10 + (step.value - 0.9) * 16}px` }">Aa</span>
          {{ t(step.label) }}
        </button>
      </div>
    </div>
    <!-- Palette. Separate from light/dark on purpose: picking a dark
         palette and leaving the mode on "System" should still follow
         Windows, into the palettes chosen for each side. -->
    <div class="row is-stacked">
      <Icon icon="ph:swatches" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.palette') }}</p>
        <p class="row-hint">{{ t('settings.paletteHint') }}</p>
      </div>
      <!-- One palette for each side, each remembered: the side on screen
           now says so, and the other shows what it will come back to. -->
      <div class="palette-sides">
        <div
          v-for="side in paletteSides"
          :key="side.mode"
          class="palette-side"
          :class="{ 'is-now': theme.currentMode.value === side.mode }"
        >
          <p class="palette-side-label">
            <Icon :icon="side.icon" class="h-3.5 w-3.5" />
            {{ t(side.label) }}
            <span v-if="theme.currentMode.value === side.mode" class="palette-side-now">
              {{ t('settings.paletteOnScreen') }}
            </span>
          </p>
          <div class="palette-grid">
            <button
              v-for="p in side.items"
              :key="p.id"
              class="palette press"
              :class="{
                'is-active': side.chosen === p.id,
                'is-live': theme.currentTheme.value === p.id,
              }"
              :title="t(p.name)"
              :aria-pressed="side.chosen === p.id"
              @click="restyle(() => theme.setTheme(p.id), $event.currentTarget)"
            >
              <span class="palette-chip" :style="{ background: p.bg }">
                <span class="palette-dot" :style="{ background: p.accent }" />
                <Icon v-if="side.chosen === p.id" icon="ph:check-bold" class="palette-tick" />
              </span>
              <span class="palette-name">{{ t(p.name) }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
    <label class="row">
      <Icon icon="ph:paint-brush-household" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.matchArt') }}</p>
        <p class="row-hint">{{ t('settings.matchArtHint') }}</p>
      </div>
      <input
        type="checkbox"
        class="switch"
        :checked="accentFromArt"
        @change="restyle(() => setAccentFromArt($event.target.checked), $event.target)"
      />
    </label>
    <!-- Typeface. Two bundled faces plus whatever Windows offers, each
         previewed in itself so the choice is visible rather than a name. -->
    <div class="row is-stacked">
      <Icon icon="ph:text-aa" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.font') }}</p>
        <p class="row-hint">{{ t('settings.fontHint') }}</p>
      </div>
      <div class="font-grid">
        <button
          v-for="f in fonts.fonts"
          :key="f.id"
          class="font-card press"
          :class="{ 'is-active': fonts.current.value === f.id }"
          :aria-pressed="fonts.current.value === f.id"
          @click="restyle(() => fonts.setFont(f.id), $event.currentTarget)"
        >
          <span class="font-sample" :style="{ fontFamily: f.display }">Aa</span>
          <span class="font-meta">
            <span class="font-name" :style="{ fontFamily: f.body }">{{ t(f.name) }}</span>
            <span class="font-note">{{ tp(f.note) }}</span>
          </span>
          <Icon
            v-if="fonts.current.value === f.id"
            icon="ph:check-circle-fill"
            class="font-tick"
          />
        </button>
      </div>
    </div>
    <div class="row">
      <Icon icon="ph:translate" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.language') }}</p>
        <p class="row-hint">{{ t('settings.languageHint') }}</p>
      </div>
      <select class="field-select w-44" :value="locale" @change="setLocale($event.target.value)">
        <option v-for="l in locales" :key="l.code" :value="l.code">{{ l.name }}</option>
      </select>
    </div>
  </section>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Icon } from '@iconify/vue'
import { useTheme } from '/src/model/theme'
import { accentFromArt, setAccentFromArt } from '/src/model/artAccent'
import { useFonts } from '/src/model/fonts'
import { ZOOM_STEPS, currentZoom, setZoom } from '/src/desktop/shortcuts'
import { restyle, resize } from '/src/model/smoothChange'
import { useI18n } from '/src/i18n'
import { tp } from '/src/i18n/platform'

const { t, locale, setLocale, locales } = useI18n()
const theme = useTheme()
const fonts = useFonts()

// Interface size lives here now, not on Ctrl and the scroll wheel. Named,
// with a sample drawn at each size: a list of percentages said nothing about
// what each would look like.
const ZOOM_NAMES = {
  0.9: 'settings.uiScaleCompact',
  1: 'settings.uiScaleDefault',
  1.1: 'settings.uiScaleComfortable',
  1.25: 'settings.uiScaleLarge',
}
const zoomSteps = ZOOM_STEPS.map((value) => ({
  value,
  label: ZOOM_NAMES[value] || `${Math.round(value * 100)}%`,
}))
const zoom = ref(currentZoom())
// The palettes, by the side they are for.
const paletteSides = computed(() => [
  {
    mode: 'dark',
    label: 'settings.paletteDark',
    icon: 'ph:moon',
    items: theme.themes.filter((p) => p.mode === 'dark'),
    chosen: theme.darkTheme.value,
  },
  {
    mode: 'light',
    label: 'settings.paletteLight',
    icon: 'ph:sun',
    items: theme.themes.filter((p) => p.mode === 'light'),
    chosen: theme.lightTheme.value,
  },
])

function pickZoom(step, anchor) {
  if (step === zoom.value) return
  const from = zoom.value
  zoom.value = step
  resize(() => setZoom(step), from, step, anchor)
}

const themeOptions = [
  { value: 'system', label: 'settings.themeSystem', icon: 'ph:desktop' },
  { value: 'light', label: 'settings.themeLight', icon: 'ph:sun' },
  { value: 'dark', label: 'settings.themeDark', icon: 'ph:moon' },
]
</script>
