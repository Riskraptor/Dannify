<template>
  <div ref="root" class="vl" :class="{ 'vl-self': !scroller }">
    <div class="vl-inner" :style="{ height: `${items.length * itemHeight}px` }">
      <div
        v-for="i in indices"
        :key="keyOf(i)"
        class="vl-row"
        :style="{ transform: `translateY(${i * itemHeight}px)`, height: `${itemHeight}px` }"
      >
        <slot :item="items[i]" :index="i" />
      </div>
    </div>
  </div>
</template>

<script setup>
import {
  ref,
  computed,
  watch,
  onMounted,
  onBeforeUnmount,
  onActivated,
  onDeactivated,
  nextTick,
} from 'vue'

// Fixed-row-height windowing. Scrolls itself, or: when `scroller` is given
// piggybacks on an ancestor's scroll container (e.g. the main view pane, so
// a long track list scrolls together with the page header like Spotify).
const props = defineProps({
  items: { type: Array, required: true },
  itemHeight: { type: Number, required: true },
  scroller: { type: Object, default: null }, // HTMLElement
  overscan: { type: Number, default: 8 },
  itemKey: { type: Function, default: null },
})

const root = ref(null)
const start = ref(0)
const end = ref(0)

const indices = computed(() => {
  const out = []
  for (let i = start.value; i < end.value; i++) out.push(i)
  return out
})

function keyOf(i) {
  const item = props.items[i]
  return props.itemKey ? props.itemKey(item, i) : i
}

function scrollEl() {
  return props.scroller || root.value
}

// Offset of the list's first row inside the scroll container's content.
function listOffset() {
  const sc = scrollEl()
  if (!props.scroller || !root.value || !sc) return 0
  return (
    root.value.getBoundingClientRect().top -
    sc.getBoundingClientRect().top +
    sc.scrollTop
  )
}

function measure() {
  const sc = scrollEl()
  if (!sc) return
  const n = props.items.length
  const h = props.itemHeight
  const top = sc.scrollTop - listOffset()
  const bottom = top + sc.clientHeight
  start.value = Math.max(0, Math.min(n, Math.floor(top / h) - props.overscan))
  end.value = Math.max(start.value, Math.min(n, Math.ceil(bottom / h) + props.overscan))
}

let raf = 0
function schedule() {
  cancelAnimationFrame(raf)
  raf = requestAnimationFrame(measure)
}

/** Scroll just enough to reveal row `i` (keyboard navigation). */
function scrollToIndex(i, { topInset = 0 } = {}) {
  const sc = scrollEl()
  if (!sc) return
  const h = props.itemHeight
  const rowTop = listOffset() + i * h
  const viewTop = sc.scrollTop + topInset
  const viewBottom = sc.scrollTop + sc.clientHeight
  if (rowTop < viewTop) sc.scrollTop = rowTop - topInset
  else if (rowTop + h > viewBottom) sc.scrollTop = rowTop + h - sc.clientHeight
}

let ro = null
let boundScroller = null
function bind() {
  unbind()
  const sc = scrollEl()
  if (!sc) return
  boundScroller = sc
  sc.addEventListener('scroll', schedule, { passive: true })
  ro = new ResizeObserver(schedule)
  ro.observe(sc)
  if (root.value && root.value !== sc) ro.observe(root.value)
  measure()
}
function unbind() {
  if (boundScroller) boundScroller.removeEventListener('scroll', schedule)
  boundScroller = null
  if (ro) ro.disconnect()
  ro = null
}

onMounted(() => nextTick(bind))
onBeforeUnmount(() => {
  unbind()
  cancelAnimationFrame(raf)
})
// Views are kept alive between visits and share the main scroll pane, so
// only listen while our view is on screen.
onActivated(() => nextTick(bind))
onDeactivated(unbind)
watch(() => props.scroller, () => nextTick(bind))
watch(() => props.items.length, () => nextTick(measure))

defineExpose({ scrollToIndex, measure })
</script>

<style scoped>
.vl-self {
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
}
.vl-inner {
  position: relative;
  width: 100%;
  /* Chromium's scroll anchoring re-targets the viewport when rows are
     swapped in and out, which fights our own scroll maths. */
  overflow-anchor: none;
}
.vl-row {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  /* Rows never affect each other's layout: skip the rest of the tree. */
  contain: layout style paint;
}
</style>
