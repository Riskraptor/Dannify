<template>
  <div class="wc" :class="{ 'is-inactive': !win.focused }" data-no-drag>
    <button
      class="wc-btn"
      :title="t('window.minimize')"
      :aria-label="t('window.minimize')"
      tabindex="-1"
      @click="desktop.minimize()"
    >
      <span v-if="fontGlyphs" class="wc-glyph">&#xE921;</span>
      <svg v-else class="wc-svg" viewBox="0 0 10 10" aria-hidden="true"><path d="M0 5.5h10" /></svg>
    </button>
    <button
      ref="maxBtn"
      class="wc-btn"
      :class="{ 'is-snap-hover': win.maxHover }"
      :title="win.maximized ? t('window.restore') : t('window.maximize')"
      :aria-label="win.maximized ? t('window.restore') : t('window.maximize')"
      tabindex="-1"
      @click="desktop.toggleMaximize()"
    >
      <span v-if="fontGlyphs" class="wc-glyph">{{ win.maximized ? '' : '' }}</span>
      <svg v-else-if="win.maximized" class="wc-svg" viewBox="0 0 10 10" aria-hidden="true">
        <rect x="0.5" y="2.5" width="7" height="7" /><path d="M2.5 2.5v-2h7v7h-2" />
      </svg>
      <svg v-else class="wc-svg" viewBox="0 0 10 10" aria-hidden="true"><rect x="0.5" y="0.5" width="9" height="9" /></svg>
    </button>
    <button
      class="wc-btn is-close"
      :title="t('window.close')"
      :aria-label="t('window.close')"
      tabindex="-1"
      @click="desktop.close()"
    >
      <span v-if="fontGlyphs" class="wc-glyph">&#xE8BB;</span>
      <svg v-else class="wc-svg is-x" viewBox="0 0 10 10" aria-hidden="true"><path d="M0.5 0.5l9 9M9.5 0.5l-9 9" /></svg>
    </button>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { bindMaxButton, desktop, platform } from '/src/desktop/bridge'
import { useI18n } from '/src/i18n'

const { t } = useI18n()
const win = desktop.state
// Windows draws these from its own icon font, so they match every other app
// there pixel for pixel. Nowhere else has that font (they came out as empty
// boxes on Linux), so elsewhere the same four shapes are drawn in lines.
const fontGlyphs = computed(() => platform.value === 'windows')

// Hovering this button has to open Windows' snap layouts, and it can only do
// that if the shell knows where the button is. Once it does, Windows owns the
// mouse there: the click arrives through the bridge instead of @click, and
// the hover state comes back as win.maxHover.
const maxBtn = ref(null)
let release = () => {}
onMounted(() => {
  // Only Windows has snap layouts to open. Elsewhere the click stays ours.
  if (platform.value === 'windows') release = bindMaxButton(maxBtn.value)
})
onBeforeUnmount(() => release())
</script>

<style scoped>
/* Caption buttons drawn with Windows' own icon font, so they match every
   other app on the system pixel for pixel. */
.wc {
  display: flex;
  align-self: stretch;
}
.wc-btn {
  display: grid;
  place-items: center;
  width: 46px;
  height: 100%;
  color: rgb(var(--c-fg) / 0.9);
  transition: background-color 0.1s linear;
}
.wc-glyph {
  font-family: 'Segoe Fluent Icons', 'Segoe MDL2 Assets';
  font-size: 10px;
  line-height: 1;
}
.wc-svg {
  width: 10px;
  height: 10px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1;
  shape-rendering: crispEdges;
}
.wc-svg.is-x {
  shape-rendering: geometricPrecision;
}
.wc-btn:hover,
.wc-btn.is-snap-hover {
  background: rgb(var(--c-tint) / 0.08);
}
.wc-btn:active {
  background: rgb(var(--c-tint) / 0.05);
  color: rgb(var(--c-fg) / 0.7);
}
.wc-btn.is-close:hover {
  background: #c42b1c;
  color: #fff;
}
.wc-btn.is-close:active {
  background: #c83c31;
  color: rgb(255 255 255 / 0.8);
}
.wc.is-inactive .wc-btn:not(:hover):not(.is-snap-hover) {
  color: rgb(var(--c-fg) / var(--fg-40));
}
</style>
