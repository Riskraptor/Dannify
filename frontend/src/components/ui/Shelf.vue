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
    <div
      ref="row"
      class="shelf-row"
      :class="{ 'is-wrap': wrap }"
      :style="{ '--card-min': `${minCard}px` }"
    >
      <slot />
    </div>
  </section>
</template>

<script setup>
import { onBeforeUnmount, onMounted, onUpdated, ref, nextTick } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  moreLabel: { type: String, default: '' },
  // Show every row instead of a single row that fits the width.
  wrap: { type: Boolean, default: false },
  minCard: { type: Number, default: 168 },
  clickableTitle: { type: Boolean, default: false },
})
defineEmits(['more'])

// A shelf shows one row and clips the rest. Clipped cards are still rendered,
// just at zero height, and each one is a focusable element: tabbing through
// the page walked into a run of things nobody can see. Mark anything below
// the first row as inert so it leaves the tab order and the screen reader.
const row = ref(null)
let observer = null
let mutations = null

function hideOverflow() {
  const el = row.value
  if (!el || props.wrap) return
  const kids = [...el.children]
  if (!kids.length) return
  const firstTop = kids[0].offsetTop
  kids.forEach((kid) => {
    const clipped = kid.offsetTop > firstTop
    if (clipped) kid.setAttribute('inert', '')
    else kid.removeAttribute('inert')
  })
}

onMounted(() => {
  nextTick(hideOverflow)
  if (typeof ResizeObserver === 'function') {
    observer = new ResizeObserver(() => hideOverflow())
    if (row.value) observer.observe(row.value)
  }
  // And whenever the cards themselves change. The row keeps its size when a
  // live search reorders them, so only a resize used to re-check, and a card
  // that moved up from a clipped place kept its inert mark: there on screen,
  // and impossible to click.
  if (typeof MutationObserver === 'function' && row.value) {
    mutations = new MutationObserver(() => hideOverflow())
    mutations.observe(row.value, { childList: true })
  }
})
onUpdated(() => nextTick(hideOverflow))
onBeforeUnmount(() => {
  if (observer) observer.disconnect()
  if (mutations) mutations.disconnect()
})
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
