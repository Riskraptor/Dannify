<template>
  <header class="vh view-pad">
    <div class="min-w-0 flex-1">
      <p v-if="eyebrow" class="eyebrow mb-1">{{ eyebrow }}</p>
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
defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  eyebrow: { type: String, default: '' },
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
.vh-title {
  font-size: 30px;
  font-weight: 700;
  line-height: 1.15;
  letter-spacing: -0.02em;
}
.vh-sub {
  margin-top: 6px;
  font-size: 13px;
  color: rgb(var(--c-fg) / 0.6);
}
.vh-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
</style>
