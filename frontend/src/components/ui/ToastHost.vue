<template>
  <Teleport to="body">
    <div class="toast-stack" aria-live="polite">
      <transition-group name="toast">
        <!-- The countdown stops while the pointer or keyboard focus is on a
             toast, so a button is never pulled away mid-reach. -->
        <div
          v-for="item in toasts"
          :key="item.id"
          class="toast"
          :class="`is-${item.tone}`"
          :role="item.tone === 'error' ? 'alert' : 'status'"
          @mouseenter="holdToasts(item.id)"
          @mouseleave="releaseToasts(item.id)"
          @focusin="holdToasts(item.id)"
          @focusout="releaseToasts(item.id)"
        >
          <Icon
            v-if="item.icon || item.tone !== 'default'"
            :icon="item.icon || toneIcon(item.tone)"
            class="h-[18px] w-[18px] shrink-0"
          />
          <span class="toast-text min-w-0 flex-1">{{ item.message }}</span>
          <!-- Said again while it was still up: counted here rather than
               stacked as a copy. Keyed by the count so the pop replays. -->
          <span v-if="item.count > 1" :key="item.count" class="toast-count">
            ×{{ item.count }}
          </span>
          <button
            v-if="item.action"
            class="toast-action"
            @click="runAction(item)"
          >
            {{ item.action.label }}
          </button>
          <button
            class="toast-close"
            :aria-label="t('common.dismiss')"
            :title="t('common.dismiss')"
            @click="dismissToast(item.id)"
          >
            <Icon icon="ph:x" class="h-3.5 w-3.5" />
          </button>
        </div>
      </transition-group>
    </div>
  </Teleport>
</template>

<script setup>
import { Icon } from '@iconify/vue'
import { useToasts } from '/src/model/toast'
import { useI18n } from '/src/i18n'

const { t } = useI18n()
const { toasts, dismissToast, holdToasts, releaseToasts } = useToasts()

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
  padding: 8px 8px 8px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  color: #fff;
  background: #2b2c31;
  box-shadow: var(--shadow-pop);
}
[data-mode='light'] .toast {
  background: #1f2227;
}
/* Wraps instead of cutting off: the end of a message is often the part that
   says what happens next. */
.toast-text {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  line-height: 1.4;
  overflow-wrap: anywhere;
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
.toast-count {
  flex-shrink: 0;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  background: rgb(255 255 255 / 0.12);
  animation: toast-count-pop 0.28s var(--ease-out);
}
@keyframes toast-count-pop {
  from {
    transform: scale(1.35);
  }
}
/* Quiet until wanted: dim, brightening under the pointer or keyboard focus. */
.toast-close {
  display: grid;
  flex-shrink: 0;
  place-items: center;
  width: 24px;
  height: 24px;
  margin-left: -4px;
  border-radius: 999px;
  color: rgb(255 255 255 / 0.55);
}
.toast-close:hover,
.toast-close:focus-visible {
  color: #fff;
  background: rgb(255 255 255 / 0.08);
}
@media (prefers-reduced-motion: reduce) {
  .toast-count {
    animation: none;
  }
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
