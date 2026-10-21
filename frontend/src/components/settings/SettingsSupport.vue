<template>
  <section>
    <h2 class="group-title">{{ t('support.title') }}</h2>

    <!-- Why: one person's free app, said warmly, once. -->
    <p class="sp-lead">
      <span class="sp-heart" aria-hidden="true"><Icon icon="ph:heart-fill" class="h-4 w-4" /></span>
      <span><b>{{ t('support.heroTitle') }}.</b> {{ support.message || t('support.heroText') }}</span>
    </p>

    <!-- The ways to give, side by side: each says who it suits. -->
    <div class="sp-ways">
      <div v-if="support.configured" class="sp-way is-kofi">
        <span class="sp-way-mark"><Icon icon="ph:coffee-fill" class="h-6 w-6" /></span>
        <p class="sp-way-name">Ko-fi</p>
        <p class="sp-way-text">{{ t('support.kofiText') }}</p>
        <button class="sp-way-btn press" @click="giveByKofi()">
          {{ t('support.give') }} <Icon icon="ph:arrow-up-right-bold" class="h-3.5 w-3.5" />
        </button>
      </div>

      <div v-if="mpesa" class="sp-way is-mpesa">
        <span class="sp-way-mark"><Icon icon="ph:device-mobile-fill" class="h-6 w-6" /></span>
        <p class="sp-way-name">M-Pesa</p>
        <p class="sp-way-text">
          {{ mpesa.kind === 'paybill' ? t('support.mpesaPaybill', { number: mpesa.number, account: mpesa.account || '—' }) : t('support.mpesaTill', { number: mpesa.number }) }}
        </p>
        <p v-if="mpesa.name" class="sp-way-note">{{ t('support.mpesaName', { name: mpesa.name }) }}</p>
        <button class="sp-way-btn press" @click="copyNumber">
          <Icon :icon="copied ? 'ph:check-bold' : 'ph:copy'" class="h-3.5 w-3.5" />
          {{ copied ? t('support.copied') : t('support.copyNumber') }}
        </button>
      </div>

      <div v-if="support.paypal_link" class="sp-way is-paypal">
        <span class="sp-way-mark"><Icon icon="ph:paypal-logo-fill" class="h-6 w-6" /></span>
        <p class="sp-way-name">PayPal</p>
        <p class="sp-way-text">{{ t('support.paypalText') }}</p>
        <button class="sp-way-btn press" @click="giveByPaypal()">
          {{ t('support.openPaypal') }} <Icon icon="ph:arrow-up-right-bold" class="h-3.5 w-3.5" />
        </button>
      </div>
    </div>

    <!-- Giving is not only money. -->
    <p class="sp-more">{{ t('support.moreTitle') }}</p>
    <div class="row">
      <Icon icon="ph:share-network" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('support.shareTitle') }}</p>
        <p class="row-hint">{{ t('support.shareText') }}</p>
      </div>
      <button class="btn" @click="copyLink">
        <Icon :icon="linkCopied ? 'ph:check-bold' : 'ph:link'" class="h-4 w-4" />
        {{ linkCopied ? t('support.linkCopied') : t('support.copyLink') }}
      </button>
    </div>
    <div v-if="reporting.status.enabled" class="row">
      <Icon icon="ph:lightbulb" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('support.ideaTitle') }}</p>
        <p class="row-hint">{{ t('support.ideaText') }}</p>
      </div>
      <button class="btn" @click="reporting.openReport()">
        <Icon icon="ph:pencil-simple-line" class="h-4 w-4" />
        {{ t('support.ideaButton') }}
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Icon } from '@iconify/vue'
import { useSupport } from '/src/model/support'
import { useReporting } from '/src/model/problems'
import { useUpdates } from '/src/model/updates'
import { copyText } from '/src/model/clipboard'
import { useI18n } from '/src/i18n'

// Supporting Dannify, on a page of its own: why, the ways to give (each
// shown only when it is set up, see support.py), and the ways to help that
// cost nothing.
const { t } = useI18n()
const { config: support, giveByKofi, giveByPaypal, gaveByMpesa } = useSupport()
const reporting = useReporting()
const updates = useUpdates()

const mpesa = computed(() => (support.mpesa && support.mpesa.number ? support.mpesa : null))

const copied = ref(false)
async function copyNumber() {
  if (!mpesa.value) return
  await copyText(mpesa.value.number)
  copied.value = true
  gaveByMpesa()
  setTimeout(() => (copied.value = false), 2000)
}
const linkCopied = ref(false)
async function copyLink() {
  await copyText(updates.siteUrl.value)
  linkCopied.value = true
  setTimeout(() => (linkCopied.value = false), 2000)
}
</script>

<style scoped>
.sp-lead {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin: 0 4px 14px;
  max-width: 70ch;
  font-size: 13.5px;
  line-height: 1.55;
  color: rgb(var(--c-fg) / 0.8);
}
.sp-lead b {
  font-weight: 800;
  color: rgb(var(--c-fg));
}
.sp-heart {
  display: grid;
  width: 26px;
  height: 26px;
  flex: none;
  place-items: center;
  border-radius: 999px;
  color: #fff;
  background: linear-gradient(150deg, #fb7185, #e11d48);
  box-shadow: 0 6px 16px rgb(225 29 72 / 0.35);
  animation: sp-beat 2.4s ease-in-out infinite;
}
.sp-ways {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 22px;
}
.sp-way {
  display: grid;
  align-content: start;
  justify-items: start;
  gap: 6px;
  padding: 18px;
  border-radius: 16px;
  background: rgb(var(--c-tint) / 0.045);
  box-shadow: inset 0 0 0 1px rgb(var(--c-tint) / 0.07);
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease;
}
[data-mode='light'] .sp-way {
  background-color: rgb(var(--c-raised));
}
.sp-way:hover {
  transform: translateY(-2px);
  box-shadow:
    inset 0 0 0 1px rgb(var(--way) / 0.45),
    0 12px 28px rgb(0 0 0 / 0.18);
}
.sp-way.is-kofi {
  --way: 255 94 91;
}
.sp-way.is-mpesa {
  --way: 22 163 74;
}
.sp-way.is-paypal {
  --way: 0 112 224;
}
.sp-way-mark {
  display: grid;
  width: 44px;
  height: 44px;
  place-items: center;
  margin-bottom: 4px;
  border-radius: 12px;
  color: #fff;
  background: rgb(var(--way));
}
.sp-way-name {
  font-size: 15px;
  font-weight: 800;
}
.sp-way-text {
  font-size: 12.5px;
  line-height: 1.45;
  color: rgb(var(--c-fg) / var(--fg-60, 0.65));
}
.sp-way-note {
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.8);
}
.sp-way-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  height: 32px;
  padding: 0 14px;
  border-radius: 999px;
  font-size: 12.5px;
  font-weight: 700;
  color: #fff;
  background: rgb(var(--way));
  transition: filter 0.15s ease;
}
.sp-way-btn:hover {
  filter: brightness(1.1);
}
.sp-more {
  margin: 0 0 9px 6px;
  font-size: 11.5px;
  font-weight: 800;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: rgb(var(--c-fg) / var(--fg-50, 0.5));
}
@keyframes sp-beat {
  0%,
  60%,
  100% {
    transform: scale(1);
  }
  70% {
    transform: scale(1.08);
  }
  80% {
    transform: scale(0.97);
  }
  90% {
    transform: scale(1.05);
  }
}
@media (prefers-reduced-motion: reduce) {
  .sp-heart {
    animation: none;
  }
}
</style>
