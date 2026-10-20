<template>
  <Teleport to="body">
    <transition name="dlg">
      <div v-if="shown" class="wnd-layer" @mousedown.self="close">
        <!-- A release with something new in it is welcomed: confetti, or
             snow on a Christmas day. -->
        <Particles v-if="shown.celebrate && !still" :kind="effect" :count="effect === 'snow' ? 60 : 80" />
        <div
          ref="box"
          v-overlay-scroll
          class="wnd menu-surface"
          :class="{ 'is-celebrating': shown.celebrate }"
          role="dialog"
          aria-modal="true"
          :aria-label="t('update.whatsNewTitle', { version: shown.version })"
          tabindex="-1"
          @keydown.stop="onKey"
        >
          <button class="icon-btn wnd-close" :title="t('common.close')" :aria-label="t('common.close')" @click="close">
            <Icon icon="ph:x" class="h-4 w-4" />
          </button>
          <header v-if="shown.celebrate" class="wnd-hero">
            <span class="wnd-hero-mark"><Icon :icon="occasion ? occasion.icon : 'ph:sparkle-fill'" class="h-7 w-7" /></span>
            <p class="wnd-hero-eyebrow">
              {{ occasion ? t(`occasion.${occasion.id}.title`, { year: occasionYear(occasion) }) : t('update.welcomeEyebrow') }}
            </p>
            <h2 class="wnd-hero-title">{{ t('update.welcomeTitle', { version: shown.version }) }}</h2>
          </header>
          <WhatsNew :version="shown.version" :notes="shown.notes" flat :bare="!!shown.celebrate" />
          <div class="wnd-actions">
            <button ref="okBtn" class="btn-accent btn-pill press px-5" @click="close">
              {{ shown.celebrate ? t('update.letsGo') : t('update.gotIt') }}
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
import Particles from '/src/components/ui/Particles.vue'
import { occasionOn, occasionYear, prefersStill } from '/src/model/occasions'

// "What's new", once, after Dannify has updated itself (model/updates.js).

const { t } = useI18n()
const shown = computed(() => whatsNew.value)
const occasion = occasionOn()
const effect = occasion ? occasion.effect : 'confetti'
const still = prefersStill()
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

watch(
  shown,
  async (now) => {
    if (!now) {
      const back = giveBack
      giveBack = null
      back?.()
      return
    }
    giveBack = rememberFocus()
    await nextTick()
    ;(okBtn.value || box.value)?.focus()
  },
  // Loaded the first time it is shown (App.vue), so already showing then.
  { immediate: true }
)
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
.wnd {
  z-index: 1;
}
.wnd.is-celebrating {
  background:
    radial-gradient(110% 70% at 50% 0%, rgb(var(--c-accent) / 0.3), transparent 70%),
    rgb(var(--c-elev));
}
.wnd-hero {
  display: grid;
  justify-items: center;
  gap: 6px;
  margin: 6px 0 18px;
  text-align: center;
}
.wnd-hero-mark {
  display: grid;
  place-items: center;
  width: 60px;
  height: 60px;
  border-radius: 18px;
  color: rgb(var(--c-accent-fg, 0 0 0));
  background: rgb(var(--c-accent));
  box-shadow: 0 14px 34px rgb(var(--c-accent) / 0.35);
  animation: wnd-pop 0.6s cubic-bezier(0.2, 0.9, 0.2, 1.25) both;
}
.wnd-hero-eyebrow {
  margin-top: 6px;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgb(var(--c-accent));
}
.wnd-hero-title {
  font-size: clamp(24px, 4vw, 32px);
  font-weight: 900;
  letter-spacing: -0.02em;
}
@keyframes wnd-pop {
  from {
    opacity: 0;
    transform: scale(0.5) rotate(-12deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .wnd-hero-mark {
    animation: none;
  }
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
