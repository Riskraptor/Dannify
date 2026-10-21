<template>
  <section>
    <h2 class="group-title">{{ t('support.title') }}</h2>

    <!-- Why: one person's free app, said warmly, once. -->
    <p class="sp-lead">
      <span class="sp-heart" aria-hidden="true"><Icon icon="ph:heart-fill" class="h-4 w-4" /></span>
      <span><b>{{ t('support.heroTitle') }}.</b> {{ support.message || t('support.heroText') }}</span>
    </p>

    <!-- M-PESA first, and plain to see: the number large, and how to pay it
         from a phone, step by step. -->
    <article v-if="mpesa" class="sp-mpesa">
      <div class="sp-mpesa-brand">
        <span class="sp-mpesa-lipa">Lipa na</span>
        <span class="sp-mpesa-mark"><Icon icon="ph:device-mobile-fill" class="h-5 w-5" />M-PESA</span>
        <span class="sp-mpesa-lead">{{ t('support.mpesaLead') }}</span>
      </div>
      <div class="sp-mpesa-number">
        <span class="sp-mpesa-label">{{ mpesa.kind === 'paybill' ? t('support.mpesaBusinessLabel') : t('support.mpesaTillLabel') }}</span>
        <span class="sp-mpesa-digits" :aria-label="mpesa.number">{{ grouped(mpesa.number) }}</span>
        <span v-if="mpesa.kind === 'paybill' && mpesa.account" class="sp-mpesa-account">{{ t('support.mpesaAccountLabel') }} {{ mpesa.account }}</span>
        <span v-if="mpesa.name" class="sp-mpesa-name">{{ t('support.mpesaName', { name: mpesa.name }) }}</span>
        <button class="sp-mpesa-copy press" @click="copyNumber">
          <Icon :icon="copied ? 'ph:check-bold' : 'ph:copy-bold'" class="h-4 w-4" />
          {{ copied ? t('support.copied') : t('support.copyNumber') }}
        </button>
      </div>
      <ol class="sp-mpesa-steps">
        <li>{{ t('support.mpesaStep1') }}</li>
        <li>{{ mpesa.kind === 'paybill' ? t('support.mpesaStep2Paybill') : t('support.mpesaStep2') }}</li>
        <li>
          {{ mpesa.kind === 'paybill' ? t('support.mpesaStep3Paybill', { number: mpesa.number, account: mpesa.account || '' }) : t('support.mpesaStep3', { number: mpesa.number }) }}
        </li>
        <li>{{ t('support.mpesaStep4') }}</li>
      </ol>
    </article>

    <!-- The ways to give from anywhere, side by side. -->
    <div class="sp-ways">
      <div v-if="support.configured" class="sp-way is-kofi">
        <span class="sp-way-mark"><Icon icon="ph:coffee-fill" class="h-6 w-6" /></span>
        <p class="sp-way-name">Ko-fi</p>
        <p class="sp-way-text">{{ t('support.kofiText') }}</p>
        <button class="sp-way-btn press" @click="giveByKofi()">
          {{ t('support.give') }} <Icon icon="ph:arrow-up-right-bold" class="h-3.5 w-3.5" />
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
      <button class="btn" @click="reporting.openReport('idea')">
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

// 8496746 reads as 849 6746, the way a number is read out and typed in.
function grouped(number) {
  const n = String(number || '')
  return n.length > 4 ? `${n.slice(0, n.length - 4)} ${n.slice(-4)}` : n
}

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
.sp-mpesa {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px 24px;
  margin-bottom: 14px;
  padding: 22px 24px;
  border-radius: 18px;
  color: #fff;
  background:
    radial-gradient(80% 120% at 100% 0%, rgb(255 255 255 / 0.14), transparent 60%),
    linear-gradient(135deg, #00a651, #007a3d);
  box-shadow: 0 16px 36px rgb(0 122 61 / 0.35);
}
.sp-mpesa-brand {
  display: grid;
  align-content: start;
  justify-items: start;
  gap: 2px;
}
.sp-mpesa-lipa {
  font-size: 13px;
  font-weight: 700;
  font-style: italic;
  opacity: 0.9;
}
.sp-mpesa-mark {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px 4px 8px;
  border-radius: 10px;
  background: #fff;
  color: #00a651;
  font-size: 22px;
  font-weight: 900;
  font-style: italic;
  letter-spacing: 0.02em;
  box-shadow: 0 4px 12px rgb(0 0 0 / 0.15);
}
.sp-mpesa-mark :deep(svg) {
  color: #e2231a;
}
.sp-mpesa-lead {
  margin-top: 8px;
  font-size: 14px;
  font-weight: 600;
  opacity: 0.95;
}
.sp-mpesa-number {
  display: grid;
  justify-items: end;
  align-content: start;
  gap: 4px;
  text-align: right;
}
.sp-mpesa-label {
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.85;
}
.sp-mpesa-digits {
  font-size: 40px;
  font-weight: 900;
  line-height: 1;
  letter-spacing: 0.04em;
  font-variant-numeric: tabular-nums;
  text-shadow: 0 2px 12px rgb(0 0 0 / 0.2);
}
.sp-mpesa-account,
.sp-mpesa-name {
  font-size: 13px;
  font-weight: 700;
}
.sp-mpesa-copy {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  height: 34px;
  padding: 0 16px;
  border-radius: 999px;
  background: #fff;
  color: #007a3d;
  font-size: 13px;
  font-weight: 800;
  box-shadow: 0 6px 16px rgb(0 0 0 / 0.18);
}
.sp-mpesa-steps {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 8px;
  counter-reset: step;
}
.sp-mpesa-steps li {
  position: relative;
  padding: 10px 12px 10px 40px;
  border-radius: 12px;
  background: rgb(0 0 0 / 0.16);
  font-size: 12.5px;
  font-weight: 600;
  line-height: 1.4;
  counter-increment: step;
}
.sp-mpesa-steps li::before {
  content: counter(step);
  position: absolute;
  top: 9px;
  left: 10px;
  display: grid;
  width: 22px;
  height: 22px;
  place-items: center;
  border-radius: 999px;
  background: #fff;
  color: #007a3d;
  font-size: 12px;
  font-weight: 900;
}
@container (max-width: 760px) {
  .sp-mpesa {
    grid-template-columns: 1fr;
  }
  .sp-mpesa-number {
    justify-items: start;
    text-align: left;
  }
}
.sp-ways {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
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
