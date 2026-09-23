<template>
  <div class="wc" :class="{ 'is-inactive': !win.focused }" data-no-drag>
    <button
      class="wc-btn"
      :title="t('window.minimize')"
      :aria-label="t('window.minimize')"
      tabindex="-1"
      @click="desktop.minimize()"
    >
      <span class="wc-glyph">&#xE921;</span>
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
      <span class="wc-glyph">{{ win.maximized ? '' : '' }}</span>
    </button>
    <button
      class="wc-btn is-close"
      :title="t('window.close')"
      :aria-label="t('window.close')"
      tabindex="-1"
      @click="desktop.close()"
    >
      <span class="wc-glyph">&#xE8BB;</span>
    </button>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { bindMaxButton, desktop } from '/src/desktop/bridge'
import { useI18n } from '/src/i18n'

const { t } = useI18n()
const win = desktop.state

// Hovering this button has to open Windows' snap layouts, and it can only do
// that if the shell knows where the button is. Once it does, Windows owns the
// mouse there: the click arrives through the bridge instead of @click, and
// the hover state comes back as win.maxHover.
const maxBtn = ref(null)
let release = () => {}
onMounted(() => {
  release = bindMaxButton(maxBtn.value)
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
  color: rgb(var(--c-fg) / 0.4);
}
</style>
