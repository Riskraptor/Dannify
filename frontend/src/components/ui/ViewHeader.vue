<template>
  <header class="vh view-pad" :class="[{ 'has-tile': tile }, tile && tile.kind]">
    <div v-if="tile" class="vh-band" aria-hidden="true" />
    <div v-if="tile" class="vh-tile" :class="tile.kind">
      <Icon :icon="tile.icon" class="vh-tile-icon" />
    </div>
    <div class="vh-text">
      <p v-if="eyebrow" class="eyebrow mb-1 truncate">{{ eyebrow }}</p>
      <h1 class="vh-title">{{ title }}</h1>
      <p v-if="subtitle || $slots.meta" class="vh-sub">
        <slot name="meta">{{ subtitle }}</slot>
      </p>
    </div>
    <div v-if="$slots.actions" class="vh-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup>
import { Icon } from '@iconify/vue'

defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  eyebrow: { type: String, default: '' },
  // { icon, kind: 'tile-songs' | 'tile-liked' | ... }: the collection's own
  // tile beside the title, and its colour behind the header.
  tile: { type: Object, default: null },
})
</script>

<style scoped>
.vh {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 16px;
  padding-top: 28px;
  padding-bottom: 20px;
}
/* A real width before the actions get any: with none, a header with a
   search box and a button squeezed its title until "Your library" broke
   over two lines. Now the actions go to a row of their own instead. */
.vh-text {
  flex: 1 1 260px;
  min-width: 0;
}
.vh-title {
  font-size: 30px;
  font-weight: 700;
  line-height: 1.15;
  letter-spacing: -0.02em;
}
.vh-sub {
  margin-top: 6px;
  font-size: 13px;
  color: rgb(var(--c-fg) / var(--fg-60));
}
.vh-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.vh {
  position: relative;
  isolation: isolate;
}
.vh.has-tile {
  align-items: flex-end;
  gap: 22px;
  padding-top: 34px;
  padding-bottom: 24px;
  background: none;
}
/* The band carries the tile's colour; the tile's own gradient stays on it. */
.vh.has-tile.tile-songs,
.vh.has-tile.tile-liked,
.vh.has-tile.tile-artists,
.vh.has-tile.tile-downloads {
  background: none;
}
.vh-band {
  position: absolute;
  inset: 0 0 -60px 0;
  z-index: -1;
  background: linear-gradient(180deg, var(--band, transparent), transparent);
  pointer-events: none;
}
.vh-tile {
  display: grid;
  place-items: center;
  width: 132px;
  height: 132px;
  flex-shrink: 0;
  border-radius: 8px;
  color: #fff;
  box-shadow: 0 10px 28px rgb(0 0 0 / 0.35);
}
.vh-tile-icon {
  width: 56px;
  height: 56px;
}
.vh.has-tile .vh-title {
  font-size: 44px;
  letter-spacing: -0.025em;
}
@media (max-width: 720px) {
  .vh-tile {
    width: 88px;
    height: 88px;
  }
  .vh-tile-icon {
    width: 38px;
    height: 38px;
  }
  .vh.has-tile .vh-title {
    font-size: 32px;
  }
}
</style>
