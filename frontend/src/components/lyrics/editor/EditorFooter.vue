<template>
  <!-- Every step's way on and way back, in the same place at the foot of the
       editor whatever the step holds, so it never has to be looked for. -->
  <footer class="foot">
    <div class="foot-start"><slot name="start" /></div>
    <p v-if="$slots.hint" class="foot-hint" aria-live="polite"><slot name="hint" /></p>
    <div class="foot-end"><slot /></div>
  </footer>
</template>

<style scoped>
.foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding: 12px 18px 14px;
  border-top: 1px solid rgb(var(--c-tint) / 0.07);
  background: rgb(var(--c-tint) / 0.02);
}
.foot-start,
.foot-end {
  display: flex;
  align-items: center;
  gap: 8px;
}
.foot-end {
  margin-left: auto;
}
.foot-hint {
  flex: 1 1 200px;
  min-width: 0;
  text-align: end;
  font-size: 12px;
  line-height: 1.45;
  color: rgb(var(--c-fg) / 0.55);
}
.foot-hint + .foot-end {
  margin-left: 0;
}
</style>
