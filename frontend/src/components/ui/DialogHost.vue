<template>
  <Teleport to="body">
    <transition name="dlg">
      <div
        v-if="current"
        :key="current.title + current.message"
        class="dlg-layer"
        @mousedown.self="cancel"
      >
        <div
          ref="box"
          class="dlg menu-surface"
          :role="current.kind === 'prompt' ? 'dialog' : 'alertdialog'"
          aria-modal="true"
          :aria-label="current.title"
          @keydown="onKey"
        >
          <div class="flex gap-4 p-5 pb-4">
            <div
              v-if="current.icon"
              class="dlg-icon"
              :class="{ 'is-danger': current.danger }"
            >
              <Icon :icon="current.icon" class="h-5 w-5" />
            </div>
            <div class="min-w-0 flex-1">
              <h2 class="text-[15px] font-semibold leading-snug">
                {{ current.title }}
              </h2>
              <p
                v-if="current.message"
                class="mt-1.5 whitespace-pre-line text-[13px] leading-relaxed text-fg/70"
              >
                {{ current.message }}
              </p>
              <p v-if="current.detail" class="mt-2 text-xs text-fg/45">
                {{ current.detail }}
              </p>
              <form v-if="current.kind === 'prompt'" class="mt-3" @submit.prevent="ok">
                <label v-if="current.label" class="dlg-label" :for="inputId">{{ current.label }}</label>
                <input
                  :id="inputId"
                  ref="field"
                  v-model="text"
                  class="dlg-input"
                  type="text"
                  spellcheck="false"
                  autocomplete="off"
                  :maxlength="current.maxLength"
                />
              </form>
            </div>
          </div>
          <div class="dlg-actions">
            <button
              v-if="current.kind === 'confirm' || current.kind === 'prompt'"
              ref="cancelBtn"
              class="btn min-w-[88px]"
              @click="cancel"
            >
              {{ current.cancelText || t('common.cancel') }}
            </button>
            <button
              ref="okBtn"
              class="min-w-[88px]"
              :class="current.danger ? 'btn-danger' : 'btn-accent'"
              :disabled="current.kind === 'prompt' && !text.trim()"
              @click="ok"
            >
              {{ current.confirmText || t('common.ok') }}
            </button>
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { computed, ref, watch, nextTick } from 'vue'
import { Icon } from '@iconify/vue'
import { useDialogs } from '/src/model/dialog'
import { useI18n } from '/src/i18n'

const { t } = useI18n()
const { queue, settleDialog } = useDialogs()
const current = computed(() => queue.value[0] || null)
const okBtn = ref(null)
const cancelBtn = ref(null)
const field = ref(null)
const text = ref('')
const inputId = 'dlg-input'

function ok() {
  if (current.value && current.value.kind === 'prompt') {
    if (!text.value.trim()) return
    settleDialog(text.value)
  } else settleDialog(true)
}
function cancel() {
  settleDialog(false)
}

function onKey(e) {
  e.stopPropagation()
  if (e.key === 'Escape') {
    e.preventDefault()
    cancel()
  } else if (e.key === 'Enter' && e.target === field.value && !e.isComposing) {
    // Here rather than left to the form, which some keyboards and input
    // methods never submit.
    e.preventDefault()
    ok()
  } else if (e.key === 'Tab') {
    // Keep focus inside the dialog.
    e.preventDefault()
    const stops = [field.value, cancelBtn.value, okBtn.value].filter(
      (el) => el && !el.disabled
    )
    if (!stops.length) return
    const at = stops.indexOf(document.activeElement)
    const next = (at + (e.shiftKey ? -1 : 1) + stops.length) % stops.length
    stops[next].focus()
  }
}

watch(current, async (d) => {
  if (!d) return
  text.value = d.kind === 'prompt' ? d.value : ''
  await nextTick()
  if (d.kind === 'prompt' && field.value) {
    field.value.focus()
    field.value.select()
    return
  }
  // Destructive actions default to Cancel so Enter can't delete by accident.
  const target = d.danger && cancelBtn.value ? cancelBtn.value : okBtn.value
  target?.focus()
})
</script>

<style scoped>
.dlg-layer {
  position: fixed;
  inset: 0;
  z-index: 1100;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgb(0 0 0 / 0.45);
}
.dlg {
  width: min(440px, 100%);
  overflow: hidden;
}
.dlg-icon {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border-radius: 999px;
  background: rgb(var(--c-accent) / 0.14);
  color: rgb(var(--c-accent));
}
.dlg-icon.is-danger {
  background: rgb(var(--c-danger) / 0.14);
  color: rgb(var(--c-danger));
}
.dlg-label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--c-fg) / var(--fg-60));
}
.dlg-input {
  width: 100%;
  height: 36px;
  padding: 0 10px;
  border-radius: 6px;
  border: 1px solid rgb(var(--c-tint) / 0.14);
  background: rgb(var(--c-tint) / 0.05);
  color: rgb(var(--c-fg));
  font-size: 14px;
  outline: none;
}
.dlg-input:focus {
  border-color: rgb(var(--c-accent));
  box-shadow: 0 0 0 1px rgb(var(--c-accent));
}
.dlg-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  background: rgb(var(--c-tint) / 0.03);
  border-top: 1px solid rgb(var(--c-tint) / 0.07);
}
.dlg-enter-active,
.dlg-leave-active {
  transition: opacity 0.14s ease;
}
.dlg-enter-active .dlg,
.dlg-leave-active .dlg {
  transition: transform 0.18s var(--ease-out);
}
.dlg-enter-from,
.dlg-leave-to {
  opacity: 0;
}
.dlg-enter-from .dlg,
.dlg-leave-to .dlg {
  transform: scale(0.96);
}
</style>
