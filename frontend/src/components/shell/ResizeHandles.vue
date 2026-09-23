<template>
  <!-- Invisible grab strips along the window edges. They hand off to the
       native Windows sizing loop, so resizing feels exactly like any other
       window (the bottom/side borders are also resizable natively). -->
  <div class="rz" aria-hidden="true">
    <div
      v-for="h in handles"
      :key="h.edge"
      class="rz-h"
      :class="`rz-${h.edge}`"
      @mousedown="beginResize($event, h.edge)"
    />
  </div>
</template>

<script setup>
import { beginResize } from '/src/desktop/bridge'

const handles = [
  { edge: 'top' },
  { edge: 'bottom' },
  { edge: 'left' },
  { edge: 'right' },
  { edge: 'top-left' },
  { edge: 'top-right' },
  { edge: 'bottom-left' },
  { edge: 'bottom-right' },
]
</script>

<style scoped>
.rz-h {
  position: fixed;
  z-index: 2000;
}
.rz-top {
  top: 0;
  left: 8px;
  right: 8px;
  height: 4px;
  cursor: ns-resize;
}
.rz-bottom {
  bottom: 0;
  left: 8px;
  right: 8px;
  height: 3px;
  cursor: ns-resize;
}
.rz-left {
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  cursor: ew-resize;
}
.rz-right {
  right: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  cursor: ew-resize;
}
.rz-top-left,
.rz-top-right,
.rz-bottom-left,
.rz-bottom-right {
  width: 8px;
  height: 8px;
}
.rz-top-left {
  top: 0;
  left: 0;
  cursor: nwse-resize;
}
.rz-top-right {
  top: 0;
  right: 0;
  cursor: nesw-resize;
}
.rz-bottom-left {
  bottom: 0;
  left: 0;
  cursor: nesw-resize;
}
.rz-bottom-right {
  bottom: 0;
  right: 0;
  cursor: nwse-resize;
}
</style>
