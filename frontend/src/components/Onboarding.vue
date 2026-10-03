<template>
  <Teleport to="body">
    <transition name="ob">
      <div
        v-if="ob.show.value"
        ref="root"
        class="ob"
        role="dialog"
        aria-modal="true"
        :aria-label="t('onboarding.label')"
        tabindex="-1"
        @keydown="onKey"
      >
        <div class="ob-glow" aria-hidden="true" />
        <button v-if="step < LAST" class="ob-skip btn-ghost" @click="finish">
          {{ t('onboarding.skip') }}
        </button>

        <div class="ob-scroll">
          <div class="ob-col">
            <transition :name="forward ? 'ob-fwd' : 'ob-bck'" mode="out-in">
              <section :key="step" class="ob-step">
                <!-- Welcome -->
                <template v-if="step === 0">
                  <img src="../assets/dannify.svg" alt="" class="ob-logo drag-none" />
                  <h1 class="ob-title">{{ t('onboarding.welcomeTitle') }}</h1>
                  <p class="ob-sub">{{ t('onboarding.welcomeText') }}</p>
                  <ul class="ob-points">
                    <li v-for="p in points" :key="p.icon" class="ob-point">
                      <span class="ob-point-icon"><Icon :icon="p.icon" class="h-5 w-5" /></span>
                      <span>
                        <span class="ob-point-title">{{ t(p.title) }}</span>
                        <span class="ob-point-text">{{ t(p.text) }}</span>
                      </span>
                    </li>
                  </ul>
                </template>

                <!-- Look -->
                <template v-else-if="step === 1">
                  <span class="ob-badge"><Icon icon="ph:palette-fill" class="h-6 w-6" /></span>
                  <h1 class="ob-title">{{ t('onboarding.lookTitle') }}</h1>
                  <p class="ob-sub">{{ t('onboarding.lookText') }}</p>
                  <div class="ob-modes" role="radiogroup" :aria-label="t('settings.theme')">
                    <button
                      v-for="m in modes"
                      :key="m.value"
                      class="ob-mode"
                      :class="{ on: theme.preference.value === m.value }"
                      role="radio"
                      :aria-checked="theme.preference.value === m.value"
                      @click="restyle(() => theme.setPreference(m.value))"
                    >
                      <Icon :icon="m.icon" class="h-4 w-4" />
                      {{ t(m.label) }}
                    </button>
                  </div>
                  <div class="ob-swatches" role="radiogroup">
                    <button
                      v-for="p in palettes"
                      :key="p.id"
                      class="ob-swatch"
                      :class="{ on: theme.currentTheme.value === p.id }"
                      role="radio"
                      :aria-checked="theme.currentTheme.value === p.id"
                      :aria-label="t(p.name)"
                      :title="t(p.name)"
                      @click="restyle(() => theme.setTheme(p.id))"
                    >
                      <span class="ob-swatch-fill" :style="{ background: p.bg }">
                        <span class="ob-swatch-dot" :style="{ background: p.accent }" />
                      </span>
                      <span class="ob-swatch-name">{{ t(p.name) }}</span>
                    </button>
                  </div>
                </template>

                <!-- Music folder -->
                <template v-else-if="step === 2">
                  <span class="ob-badge"><Icon icon="ph:folder-simple-fill" class="h-6 w-6" /></span>
                  <h1 class="ob-title">{{ t('onboarding.folderTitle') }}</h1>
                  <p class="ob-sub">{{ t('onboarding.folderText') }}</p>
                  <div class="ob-folder">
                    <Icon icon="ph:music-notes-simple" class="ob-folder-icon h-5 w-5" />
                    <span class="ob-folder-path" :title="folder">{{ folder || t('settings.notSet') }}</span>
                    <button class="btn" :disabled="picking" @click="changeFolder">
                      {{ t('onboarding.change') }}
                    </button>
                  </div>
                  <p class="ob-note">{{ t('onboarding.folderNote') }}</p>
                </template>

                <!-- Account -->
                <template v-else-if="step === 3">
                  <span class="ob-badge"><Icon icon="ph:user-circle-fill" class="h-6 w-6" /></span>
                  <h1 class="ob-title">{{ t('onboarding.accountTitle') }}</h1>
                  <p class="ob-sub">{{ t('onboarding.accountText') }}</p>
                  <div v-if="account.signedIn.value" class="ob-signed">
                    <Icon icon="ph:check-circle-fill" class="h-5 w-5" />
                    {{ t('account.signedInAs', { name: account.displayName.value }) }}
                  </div>
                  <button
                    v-else
                    class="btn-accent btn-pill btn-lg ob-google"
                    :disabled="account.busy.value"
                    @click="account.signIn()"
                  >
                    <Icon icon="ph:google-logo-bold" class="h-4 w-4" />
                    {{ account.busy.value ? t('account.connecting') : t('account.connect') }}
                  </button>
                  <p class="ob-note">{{ t('onboarding.accountNote') }}</p>
                </template>

                <!-- Done -->
                <template v-else>
                  <span class="ob-done"><Icon icon="ph:check-bold" class="h-9 w-9" /></span>
                  <h1 class="ob-title">{{ t('onboarding.doneTitle') }}</h1>
                  <p class="ob-sub">{{ t('onboarding.doneText') }}</p>
                </template>
              </section>
            </transition>

            <footer class="ob-foot">
              <div class="ob-dots" aria-hidden="true">
                <span v-for="i in LAST + 1" :key="i" :class="{ on: i - 1 === step, past: i - 1 < step }" />
              </div>
              <div class="ob-nav">
                <button v-if="step > 0 && step < LAST" class="btn-ghost btn-lg" @click="go(step - 1)">
                  {{ t('onboarding.back') }}
                </button>
                <button
                  ref="primary"
                  class="btn-pill btn-lg ob-primary"
                  :class="laterOnly ? 'btn' : 'btn-accent'"
                  @click="advance"
                >
                  {{ primaryLabel }}
                  <Icon v-if="step < LAST" icon="ph:arrow-right-bold" class="h-4 w-4" />
                </button>
              </div>
            </footer>
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { restyle } from '/src/model/smoothChange'
import { computed, nextTick, ref, watch } from 'vue'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { useOnboarding } from '/src/model/onboarding'
import { useTheme, THEMES } from '/src/model/theme'
import { useSettingsManager } from '/src/model/settings'
import { useAccount } from '/src/model/account'
import { useUi } from '/src/model/ui'
import { trapTab } from '/src/model/focusTrap'

const { t } = useI18n()
const ob = useOnboarding()
const theme = useTheme()
const sm = useSettingsManager()
const account = useAccount()
const ui = useUi()

const LAST = 4
const step = ref(0)
const forward = ref(true)
const root = ref(null)
const primary = ref(null)
const picking = ref(false)

const points = [
  { icon: 'ph:play-circle-fill', title: 'onboarding.listenTitle', text: 'onboarding.listenText' },
  { icon: 'ph:download-simple-bold', title: 'onboarding.saveTitle', text: 'onboarding.saveText' },
  { icon: 'ph:microphone-stage-fill', title: 'onboarding.lyricsTitle', text: 'onboarding.lyricsText' },
]
const modes = [
  { value: 'system', label: 'settings.themeSystem', icon: 'ph:desktop' },
  { value: 'dark', label: 'settings.themeDark', icon: 'ph:moon' },
  { value: 'light', label: 'settings.themeLight', icon: 'ph:sun' },
]
// The palettes for the mode on screen now: picking one of the other mode's
// would flip the whole app, which is not what a click on a colour means.
const palettes = computed(() => THEMES.filter((p) => p.mode === theme.currentMode.value))
const folder = computed(() => sm.settings.value.download_dir || '')

// On the sign-in step the green button is Google's; moving on without it is
// the quieter choice.
const laterOnly = computed(() => step.value === 3 && !account.signedIn.value)
const primaryLabel = computed(() => {
  if (step.value === LAST) return t('onboarding.start')
  if (laterOnly.value) return t('onboarding.notNow')
  return t('onboarding.continue')
})

function go(to) {
  forward.value = to > step.value
  step.value = Math.max(0, Math.min(LAST, to))
}

function advance() {
  if (step.value < LAST) go(step.value + 1)
  else finish()
}

async function changeFolder() {
  picking.value = true
  try {
    await sm.pickDownloadFolder()
  } finally {
    picking.value = false
  }
}

async function finish() {
  ob.finish()
  // Straight into the one thing to do next: look for some music.
  await nextTick()
  ui.focusSearch()
}

function onKey(e) {
  if (e.key === 'Escape') {
    e.preventDefault()
    finish()
  } else if (e.key === 'Tab') {
    trapTab(e, root.value)
  } else if (e.key === 'ArrowRight' && e.target === root.value) {
    advance()
  } else if (e.key === 'ArrowLeft' && e.target === root.value && step.value > 0 && step.value < LAST) {
    go(step.value - 1)
  }
  // Keys pressed here are for the welcome, not the player behind it.
  if (e.key !== 'F11') e.stopPropagation()
}

watch(
  () => ob.show.value,
  async (open) => {
    if (!open) return
    step.value = 0
    await nextTick()
    primary.value?.focus()
  }
)
watch(step, async () => {
  await nextTick()
  primary.value?.focus()
})
</script>

<style scoped>
.ob {
  position: fixed;
  /* Below the title bar, which stays usable: the window can still be moved,
     minimised or closed while this is up. */
  inset: var(--titlebar-h, 40px) 0 0 0;
  z-index: 1050;
  overflow: hidden;
  background: rgb(var(--c-app));
  color: rgb(var(--c-fg));
}
/* Centred while it fits, scrollable when the window is short: auto margins
   never push the top out of reach the way centring alignment does. */
.ob-scroll {
  position: absolute;
  inset: 0;
  display: flex;
  overflow-y: auto;
  padding: 32px 24px;
}
.ob:focus {
  outline: none;
}
.ob-glow {
  position: absolute;
  inset: -30% -10% auto -10%;
  height: 90%;
  pointer-events: none;
  background:
    radial-gradient(40% 55% at 30% 30%, rgb(var(--c-accent) / 0.22), transparent 70%),
    radial-gradient(45% 50% at 78% 70%, rgb(var(--c-accent) / 0.1), transparent 70%);
  animation: ob-drift 14s ease-in-out infinite alternate;
}
@keyframes ob-drift {
  to {
    transform: translate3d(4%, 6%, 0) scale(1.05);
  }
}
.ob-skip {
  position: absolute;
  z-index: 1;
  top: 16px;
  right: 20px;
}
.ob-col {
  position: relative;
  display: flex;
  width: min(560px, 100%);
  margin: auto;
  flex-direction: column;
  align-items: stretch;
}
/* Every step as tall as the tallest, so Back and Continue stay put. */
.ob-step {
  display: flex;
  min-height: 430px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}
.ob-logo {
  width: 84px;
  height: 84px;
  filter: drop-shadow(0 18px 36px rgb(var(--c-accent) / 0.35));
}
.ob-badge,
.ob-done {
  display: grid;
  width: 64px;
  height: 64px;
  place-items: center;
  border-radius: 20px;
  color: rgb(var(--c-accent));
  background: rgb(var(--c-accent) / 0.12);
}
.ob-done {
  width: 76px;
  height: 76px;
  border-radius: 999px;
  color: rgb(var(--c-accent-fg));
  background: rgb(var(--c-accent));
  box-shadow: 0 16px 40px rgb(var(--c-accent) / 0.35);
  animation: ob-pop 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
}
@keyframes ob-pop {
  from {
    transform: scale(0.6);
    opacity: 0;
  }
}
.ob-title {
  margin-top: 22px;
  font-family: var(--font-display, theme('fontFamily.display'));
  font-size: 30px;
  font-weight: 800;
  letter-spacing: -0.02em;
  line-height: 1.15;
}
.ob-sub {
  margin-top: 10px;
  max-width: 440px;
  font-size: 14.5px;
  line-height: 1.55;
  color: rgb(var(--c-fg) / 0.66);
}
.ob-points {
  display: grid;
  width: 100%;
  margin-top: 26px;
  gap: 10px;
  text-align: left;
}
.ob-point {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 14px;
  border: 1px solid rgb(var(--c-tint) / 0.08);
  border-radius: 14px;
  background: rgb(var(--c-tint) / 0.035);
}
.ob-point-icon {
  display: grid;
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  place-items: center;
  border-radius: 11px;
  color: rgb(var(--c-accent));
  background: rgb(var(--c-accent) / 0.12);
}
.ob-point-title {
  display: block;
  font-size: 14px;
  font-weight: 650;
}
.ob-point-text {
  display: block;
  margin-top: 2px;
  font-size: 13px;
  color: rgb(var(--c-fg) / 0.6);
}
.ob-modes {
  display: inline-flex;
  margin-top: 24px;
  padding: 4px;
  gap: 4px;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.06);
}
.ob-mode {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  padding: 0 16px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.7);
  transition: background-color 0.15s, color 0.15s;
}
.ob-mode:hover {
  color: rgb(var(--c-fg));
}
.ob-mode.on {
  color: rgb(var(--c-accent-fg));
  background: rgb(var(--c-accent));
}
.ob-swatches {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  margin-top: 20px;
  gap: 12px;
}
.ob-swatch {
  display: flex;
  width: 86px;
  flex-direction: column;
  align-items: center;
  gap: 7px;
  padding: 8px 6px;
  border-radius: 14px;
  transition: background-color 0.15s;
}
.ob-swatch:hover {
  background: rgb(var(--c-tint) / 0.05);
}
.ob-swatch-fill {
  position: relative;
  display: block;
  width: 58px;
  height: 40px;
  border: 1px solid rgb(var(--c-tint) / 0.16);
  border-radius: 11px;
  transition: box-shadow 0.15s;
}
.ob-swatch.on .ob-swatch-fill {
  box-shadow: 0 0 0 2px rgb(var(--c-app)), 0 0 0 4px rgb(var(--c-accent));
}
.ob-swatch-dot {
  position: absolute;
  right: 7px;
  bottom: 7px;
  width: 14px;
  height: 14px;
  border-radius: 999px;
}
.ob-swatch-name {
  font-size: 12px;
  color: rgb(var(--c-fg) / 0.7);
}
.ob-folder {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 12px;
  margin-top: 26px;
  padding: 10px 10px 10px 16px;
  border: 1px solid rgb(var(--c-tint) / 0.1);
  border-radius: 14px;
  background: rgb(var(--c-tint) / 0.04);
  text-align: left;
}
.ob-folder-icon {
  flex-shrink: 0;
  color: rgb(var(--c-accent));
}
.ob-folder-path {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  font-size: 13.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
  direction: rtl;
  text-align: left;
}
.ob-note {
  margin-top: 12px;
  font-size: 12.5px;
  color: rgb(var(--c-fg) / 0.5);
}
.ob-google {
  margin-top: 26px;
  gap: 8px;
}
.ob-signed {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 26px;
  padding: 10px 16px;
  border-radius: 999px;
  font-size: 13.5px;
  font-weight: 600;
  color: rgb(var(--c-accent));
  background: rgb(var(--c-accent) / 0.12);
}
.ob-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 30px;
}
.ob-dots {
  display: flex;
  gap: 6px;
}
.ob-dots span {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.18);
  transition: width 0.25s, background-color 0.25s;
}
.ob-dots span.past {
  background: rgb(var(--c-accent) / 0.5);
}
.ob-dots span.on {
  width: 22px;
  background: rgb(var(--c-accent));
}
.ob-nav {
  display: flex;
  gap: 8px;
}
.ob-primary {
  min-width: 140px;
  gap: 8px;
}

/* The overlay itself fades; the steps slide, in the direction travelled. */
.ob-enter-active,
.ob-leave-active {
  transition: opacity 0.3s ease;
}
.ob-enter-from,
.ob-leave-to {
  opacity: 0;
}
.ob-fwd-enter-active,
.ob-fwd-leave-active,
.ob-bck-enter-active,
.ob-bck-leave-active {
  transition: opacity 0.22s ease, transform 0.28s cubic-bezier(0.2, 0.8, 0.2, 1);
}
.ob-fwd-enter-from,
.ob-bck-leave-to {
  opacity: 0;
  transform: translateX(24px);
}
.ob-fwd-leave-to,
.ob-bck-enter-from {
  opacity: 0;
  transform: translateX(-24px);
}
@media (prefers-reduced-motion: reduce) {
  .ob-glow,
  .ob-done {
    animation: none;
  }
  .ob-fwd-enter-active,
  .ob-fwd-leave-active,
  .ob-bck-enter-active,
  .ob-bck-leave-active {
    transition: opacity 0.12s ease;
  }
  .ob-fwd-enter-from,
  .ob-fwd-leave-to,
  .ob-bck-enter-from,
  .ob-bck-leave-to {
    transform: none;
  }
}
@media (max-height: 660px) {
  .ob-scroll {
    padding: 20px 24px;
  }
  .ob-step {
    min-height: 0;
  }
  .ob-logo {
    width: 56px;
    height: 56px;
  }
  .ob-badge {
    width: 52px;
    height: 52px;
    border-radius: 16px;
  }
  .ob-done {
    width: 64px;
    height: 64px;
  }
  .ob-title {
    margin-top: 14px;
    font-size: 26px;
  }
  .ob-sub {
    margin-top: 6px;
  }
  .ob-points {
    margin-top: 16px;
    gap: 8px;
  }
  .ob-point {
    padding: 9px 12px;
  }
  .ob-point-icon {
    width: 32px;
    height: 32px;
    border-radius: 9px;
  }
  .ob-modes,
  .ob-folder,
  .ob-google,
  .ob-signed {
    margin-top: 18px;
  }
  .ob-foot {
    margin-top: 20px;
  }
}
</style>
