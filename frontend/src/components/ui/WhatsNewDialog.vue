<template>
  <Teleport to="body">
    <transition name="dlg">
      <div v-if="shown" class="wnd-layer" @mousedown.self="close">
        <div
          ref="box"
          v-overlay-scroll
          class="wnd menu-surface"
          role="dialog"
          aria-modal="true"
          :aria-label="t('update.whatsNewTitle', { version: shown.version })"
          tabindex="-1"
          @keydown.stop="onKey"
        >
          <button class="icon-btn wnd-close" :title="t('common.close')" :aria-label="t('common.close')" @click="close">
            <Icon icon="ph:x" class="h-4 w-4" />
          </button>
          <WhatsNew :version="shown.version" :notes="shown.notes" flat />
          <div class="wnd-actions">
            <button ref="okBtn" class="btn-accent btn-pill press px-5" @click="close">
              {{ t('update.gotIt') }}
            </button>
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { Icon } from '@iconify/vue'
import { whatsNew } from '/src/model/updates'
import { rememberFocus, trapTab } from '/src/model/focusTrap'
import { useI18n } from '/src/i18n'
import WhatsNew from '/src/components/ui/WhatsNew.vue'

// "What's new", once, after Dannify has updated itself (model/updates.js).

const { t } = useI18n()
const shown = computed(() => whatsNew.value)
const box = ref(null)
const okBtn = ref(null)
let giveBack = null

function close() {
  whatsNew.value = null
}

function onKey(e) {
  if (e.key === 'Escape') {
    e.preventDefault()
    close()
    return
  }
  trapTab(e, box.value)
}

watch(shown, async (now) => {
  if (!now) {
    const back = giveBack
    giveBack = null
    back?.()
    return
  }
  giveBack = rememberFocus()
  await nextTick()
  ;(okBtn.value || box.value)?.focus()
})
</script>

<style scoped>
.wnd-layer {
  position: fixed;
  inset: 0;
  z-index: 1100;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgb(0 0 0 / 0.5);
}
.wnd {
  position: relative;
  width: min(680px, 100%);
  max-height: min(84vh, 760px);
  overflow-y: auto;
  padding: 24px 24px 20px;
  border-radius: 18px;
  background:
    radial-gradient(90% 60% at 0% 0%, rgb(var(--c-accent) / 0.16), transparent 70%),
    rgb(var(--c-elev));
}
.wnd-close {
  position: absolute;
  top: 14px;
  right: 14px;
}
.wnd-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 18px;
}
@media (width <= 560px) {
  .wnd {
    padding: 20px 16px 16px;
  }
}
</style>
