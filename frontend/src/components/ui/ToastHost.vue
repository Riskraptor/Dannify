<template>
  <Teleport to="body">
    <div class="toast-stack" aria-live="polite">
      <transition-group name="toast">
        <div
          v-for="item in toasts"
          :key="item.id"
          class="toast"
          :class="`is-${item.tone}`"
          role="status"
        >
          <Icon
            v-if="item.icon || item.tone !== 'default'"
            :icon="item.icon || toneIcon(item.tone)"
            class="h-[18px] w-[18px] shrink-0"
          />
          <span class="min-w-0 flex-1 truncate">{{ item.message }}</span>
          <button
            v-if="item.action"
            class="toast-action"
            @click="runAction(item)"
          >
            {{ item.action.label }}
          </button>
        </div>
      </transition-group>
    </div>
  </Teleport>
</template>

<script setup>
import { Icon } from '@iconify/vue'
import { useToasts } from '/src/model/toast'

const { toasts, dismissToast } = useToasts()

function toneIcon(tone) {
  if (tone === 'success') return 'ph:check-circle-fill'
  if (tone === 'error') return 'ph:warning-circle-fill'
  return 'ph:info'
}

function runAction(item) {
  dismissToast(item.id)
  item.action.run()
}
</script>

<style scoped>
.toast-stack {
  position: fixed;
  left: 50%;
  bottom: calc(var(--player-h) + 12px);
  z-index: 1050;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  transform: translateX(-50%);
  pointer-events: none;
  width: min(480px, calc(100vw - 32px));
}
.toast {
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 40px;
  max-width: 100%;
  padding: 8px 10px 8px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  color: #fff;
  background: #2b2c31;
  box-shadow: var(--shadow-pop);
}
[data-theme='dannify-light'] .toast {
  background: #1f2227;
}
.toast.is-success svg {
  color: rgb(26 208 92);
}
.toast.is-error svg {
  color: rgb(242 109 109);
}
.toast-action {
  flex-shrink: 0;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  color: rgb(26 208 92);
}
.toast-action:hover {
  background: rgb(255 255 255 / 0.08);
}
.toast-enter-active,
.toast-leave-active {
  transition:
    opacity 0.18s ease,
    transform 0.22s var(--ease-out);
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
.toast-leave-active {
  position: absolute;
}
</style>
