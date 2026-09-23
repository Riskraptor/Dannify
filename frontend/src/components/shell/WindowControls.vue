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
      class="wc-btn"
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
import { desktop } from '/src/desktop/bridge'
import { useI18n } from '/src/i18n'

const { t } = useI18n()
const win = desktop.state
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
.wc-btn:hover {
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
.wc.is-inactive .wc-btn:not(:hover) {
  color: rgb(var(--c-fg) / 0.4);
}
</style>
