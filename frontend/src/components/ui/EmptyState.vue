<template>
  <div class="empty" :class="{ 'is-compact': compact }">
    <div class="empty-icon">
      <Icon :icon="icon" class="h-7 w-7" />
    </div>
    <p class="empty-title">{{ title }}</p>
    <p v-if="text" class="empty-text">{{ text }}</p>
    <div v-if="$slots.default" class="empty-actions">
      <slot />
    </div>
  </div>
</template>

<script setup>
import { Icon } from '@iconify/vue'

defineProps({
  icon: { type: String, default: 'ph:music-notes' },
  title: { type: String, required: true },
  text: { type: String, default: '' },
  compact: { type: Boolean, default: false },
})
</script>

<style scoped>
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 72px 24px;
  text-align: center;
}
.empty.is-compact {
  padding: 40px 16px;
}
.empty-icon {
  display: grid;
  place-items: center;
  width: 64px;
  height: 64px;
  margin-bottom: 16px;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.06);
  color: rgb(var(--c-fg) / var(--fg-45));
}
.empty-title {
  font-size: 18px;
  font-weight: 700;
}
.empty-text {
  max-width: 420px;
  margin-top: 6px;
  font-size: 13.5px;
  line-height: 1.5;
  color: rgb(var(--c-fg) / var(--fg-60));
}
.empty-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 20px;
}
</style>
