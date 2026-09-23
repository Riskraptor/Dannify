<template>
  <section class="shelf">
    <header class="shelf-head">
      <h2 class="shelf-title">
        <a v-if="clickableTitle" class="link" @click="$emit('more')">{{ title }}</a>
        <template v-else>{{ title }}</template>
      </h2>
      <button v-if="moreLabel" class="shelf-more" @click="$emit('more')">
        {{ moreLabel }}
      </button>
    </header>
    <div class="shelf-row" :class="{ 'is-wrap': wrap }" :style="{ '--card-min': `${minCard}px` }">
      <slot />
    </div>
  </section>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  moreLabel: { type: String, default: '' },
  // Show every row instead of a single row that fits the width.
  wrap: { type: Boolean, default: false },
  minCard: { type: Number, default: 168 },
  clickableTitle: { type: Boolean, default: false },
})
defineEmits(['more'])
</script>

<style scoped>
.shelf {
  margin-bottom: 28px;
}
.shelf-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 6px;
  padding: 0 10px;
}
.shelf-title {
  font-size: 21px;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.shelf-more {
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.55);
}
.shelf-more:hover {
  color: rgb(var(--c-fg));
  text-decoration: underline;
}
/* One row that fits the pane width: extra cards are clipped, like the
   shelves in streaming apps. */
.shelf-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--card-min), 1fr));
  grid-template-rows: auto;
  grid-auto-rows: 0;
  column-gap: 6px;
  overflow: hidden;
}
.shelf-row.is-wrap {
  grid-auto-rows: auto;
  row-gap: 6px;
}
</style>
