<template>
  <section>
    <h2 class="group-title">{{ t('support.title') }}</h2>

    <!-- Why: one person's free app, said warmly, once. -->
    <p class="sp-lead">
      <span class="sp-heart" aria-hidden="true"><Icon icon="ph:heart-fill" class="h-4 w-4" /></span>
      <span><b>{{ t('support.heroTitle') }}.</b> {{ support.message || t('support.heroText') }}</span>
    </p>

    <!-- Just gave: thank you, there and then. -->
    <article v-if="thanked" class="sp-thanks">
      <Particles :look="{ shape: 'heart', motion: 'rise', palette: ['#ffd1dc', '#ff8fab', '#fda4af'] }" :count="18" contain fall="220px" />
      <span class="sp-thanks-heart"><Icon icon="ph:heart-fill" class="h-7 w-7" /></span>
      <div class="min-w-0">
        <h3 class="sp-thanks-title">{{ t('support.thanksTitle') }}</h3>
        <p class="sp-thanks-text">{{ t('support.thanksText') }}</p>
      </div>
    </article>

    <!-- PayPal, the way to give from anywhere: first, and inside the app. -->
    <article v-if="support.paypal_link" class="sp-paypal">
      <div class="sp-paypal-main">
        <span class="sp-paypal-mark" aria-label="PayPal"><b>Pay</b><i>Pal</i></span>
        <h3 class="sp-paypal-title">{{ t('support.paypalTitle') }}</h3>
        <p class="sp-paypal-text">{{ t('support.paypalLead') }}</p>
        <div class="sp-tiers">
          <button v-for="tier in tiers" :key="tier.label" class="sp-tier press" :disabled="checkingOut" @click="giveByPaypal()">
            <Icon :icon="tier.icon" class="h-4 w-4" />
            <span>{{ t(tier.label) }}</span>
            <b>{{ price(tier.usd) }}</b>
          </button>
        </div>
      </div>
      <div class="sp-paypal-side">
        <button class="sp-paypal-btn press" :disabled="checkingOut" @click="giveByPaypal()">
          <span v-if="checkingOut" class="spinner h-4 w-4" />
          <Icon v-else icon="ph:paypal-logo-fill" class="h-5 w-5" />
          {{ checkingOut ? t('support.checkoutOpen') : t('support.paypalGive') }}
        </button>
        <button class="sp-paypal-alt" @click="giveByPaypal({ inBrowser: true })">
          {{ t('support.inBrowser') }} <Icon icon="ph:arrow-up-right-bold" class="h-3 w-3" />
        </button>
        <p class="sp-paypal-safe"><Icon icon="ph:lock-simple-fill" class="h-3.5 w-3.5" />{{ t('support.paypalSafe') }}</p>
      </div>
    </article>

    <!-- In Kenya, M-PESA too, plain to see: the number large, and how to pay
         it from a phone, step by step. Elsewhere it is a card among the
         others: Dannify is used all over the world. -->
    <article v-if="mpesa && inKenya" class="sp-mpesa">
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
          <Icon :icon="copied ? 'ph:check-bold' : 'ph:copy'" class="h-4 w-4" />
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

    <!-- The other ways, side by side. -->
    <div class="sp-ways">
      <div v-if="support.configured" class="sp-way is-kofi">
        <span class="sp-way-mark"><Icon icon="ph:coffee-fill" class="h-6 w-6" /></span>
        <p class="sp-way-name">Ko-fi</p>
        <p class="sp-way-text">{{ t('support.kofiText') }}</p>
        <button class="sp-way-btn press" @click="giveByKofi()">
          {{ t('support.give') }} <Icon icon="ph:arrow-up-right-bold" class="h-3.5 w-3.5" />
        </button>
      </div>


      <div v-if="mpesa && !inKenya" class="sp-way is-mpesa">
        <span class="sp-way-mark is-mpesa-mark">M-PESA</span>
        <p class="sp-way-name">M-PESA</p>
        <p class="sp-way-text">{{ t('support.mpesaKenya', { number: grouped(mpesa.number) }) }}</p>
        <button class="sp-way-btn press" @click="copyNumber">
          <Icon :icon="copied ? 'ph:check-bold' : 'ph:copy'" class="h-3.5 w-3.5" />
          {{ copied ? t('support.copied') : t('support.copyNumber') }}
        </button>
      </div>

    </div>

    <!-- Giving is not only money. -->
    <p class="sp-more">{{ t('support.moreTitle') }}</p>
    <div class="row">
      <Icon icon="ph:link" class="row-icon" />
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
        <Icon icon="ph:pencil-simple" class="h-4 w-4" />
        {{ t('support.ideaButton') }}
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed, defineAsyncComponent, ref } from 'vue'
import { Icon } from '@iconify/vue'
import { checkingOut, thankedAt, useSupport } from '/src/model/support'
import { region } from '/src/model/occasions'
import { useReporting } from '/src/model/problems'
import { useUpdates } from '/src/model/updates'
import { copyText } from '/src/model/clipboard'
import { useI18n } from '/src/i18n'

// Supporting Dannify, on a page of its own: why, the ways to give (each
// shown only when it is set up, see support.py), and the ways to help that
// cost nothing.
const { t, locale } = useI18n()
const Particles = defineAsyncComponent(() => import('/src/components/ui/Particles.vue'))
const { config: support, giveByKofi, giveByPaypal, gaveByMpesa } = useSupport()
const reporting = useReporting()
const updates = useUpdates()

const mpesa = computed(() => (support.mpesa && support.mpesa.number ? support.mpesa : null))

// What the PayPal checkout offers (made with these, in USD): chosen there.
const tiers = [
  { label: 'support.tierCoffee', icon: 'ph:coffee-fill', usd: 3 },
  { label: 'support.tierLunch', icon: 'ph:bowl-food-fill', usd: 10 },
  { label: 'support.tierThanks', icon: 'ph:heart-fill', usd: 25 },
]
function price(usd) {
  return new Intl.NumberFormat(locale.value || 'en', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(usd)
}
// Thanked for a while after giving, then the page is as it was.
const thanked = computed(() => thankedAt.value > 0 && Date.now() - thankedAt.value < 30 * 60 * 1000)
// Where the app thinks it is (Settings, Special days): a Kenyan till is the
// way to give in Kenya, and a curiosity anywhere else.
const inKenya = computed(() => region.value === 'KE')

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
/* PayPal, first: its blues, its two-tone name, the amounts it offers. */
.sp-paypal {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px 28px;
  margin-bottom: 14px;
  padding: 24px;
  border-radius: 18px;
  color: #fff;
  background:
    radial-gradient(70% 120% at 100% 0%, rgb(255 255 255 / 0.16), transparent 60%),
    linear-gradient(135deg, #003087, #0070e0);
  box-shadow: 0 16px 36px rgb(0 48 135 / 0.35);
}
.sp-paypal-main {
  display: grid;
  justify-items: start;
  gap: 6px;
  min-width: 0;
}
.sp-paypal-mark {
  display: inline-flex;
  padding: 3px 12px;
  border-radius: 10px;
  background: #fff;
  font-size: 22px;
  font-weight: 900;
  font-style: italic;
  letter-spacing: -0.01em;
  box-shadow: 0 4px 12px rgb(0 0 0 / 0.15);
}
.sp-paypal-mark b {
  color: #003087;
}
.sp-paypal-mark i {
  color: #009cde;
}
.sp-paypal-title {
  margin-top: 6px;
  font-size: 19px;
  font-weight: 800;
  letter-spacing: -0.01em;
}
.sp-paypal-text {
  max-width: 56ch;
  font-size: 13.5px;
  line-height: 1.5;
  color: rgb(255 255 255 / 0.85);
}
.sp-tiers {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}
.sp-tier {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 14px;
  border-radius: 999px;
  background: rgb(255 255 255 / 0.14);
  box-shadow: inset 0 0 0 1px rgb(255 255 255 / 0.22);
  font-size: 13px;
  font-weight: 600;
  transition:
    background-color 0.15s ease,
    transform 0.15s ease;
}
.sp-tier:hover:not(:disabled) {
  background: rgb(255 255 255 / 0.24);
  transform: translateY(-1px);
}
.sp-tier b {
  font-weight: 900;
}
.sp-paypal-side {
  display: grid;
  align-content: center;
  justify-items: stretch;
  gap: 10px;
  min-width: 220px;
}
.sp-paypal-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 46px;
  padding: 0 22px;
  border-radius: 999px;
  background: #ffc439;
  color: #111;
  font-size: 15px;
  font-weight: 800;
  box-shadow: 0 8px 22px rgb(0 0 0 / 0.25);
  transition:
    filter 0.15s ease,
    transform 0.15s ease;
}
.sp-paypal-btn:hover:not(:disabled) {
  filter: brightness(1.05);
  transform: translateY(-1px);
}
.sp-paypal-btn:disabled {
  opacity: 0.85;
  cursor: progress;
}
.sp-paypal-alt {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  font-size: 12.5px;
  font-weight: 700;
  color: rgb(255 255 255 / 0.85);
}
.sp-paypal-alt:hover {
  color: #fff;
  text-decoration: underline;
}
.sp-paypal-safe {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  max-width: 260px;
  font-size: 11.5px;
  line-height: 1.4;
  color: rgb(255 255 255 / 0.75);
}
.sp-paypal-safe :deep(svg) {
  flex: none;
  margin-top: 1px;
}
@container (max-width: 760px) {
  .sp-paypal {
    grid-template-columns: 1fr;
  }
  .sp-paypal-side {
    justify-items: start;
    min-width: 0;
  }
}
/* Thank you: warm, and gone after a while. */
.sp-thanks {
  position: relative;
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 14px;
  padding: 22px 24px;
  overflow: hidden;
  border-radius: 18px;
  color: #fff;
  background: linear-gradient(135deg, #e11d48, #fb7185);
  box-shadow: 0 16px 36px rgb(225 29 72 / 0.35);
  animation: sp-thanks-in 0.6s cubic-bezier(0.2, 0.9, 0.2, 1.2) both;
}
.sp-thanks-heart {
  position: relative;
  z-index: 1;
  display: grid;
  width: 56px;
  height: 56px;
  flex: none;
  place-items: center;
  border-radius: 999px;
  background: rgb(255 255 255 / 0.2);
  animation: sp-beat 1.6s ease-in-out infinite;
}
.sp-thanks-title {
  position: relative;
  z-index: 1;
  font-size: 20px;
  font-weight: 900;
}
.sp-thanks-text {
  position: relative;
  z-index: 1;
  font-size: 13.5px;
  color: rgb(255 255 255 / 0.9);
}
@keyframes sp-thanks-in {
  from {
    opacity: 0;
    transform: scale(0.96);
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
.sp-way.is-mpesa {
  --way: 0 166 81;
}
.sp-way-mark.is-mpesa-mark {
  width: auto;
  padding: 0 10px;
  font-size: 13px;
  font-weight: 900;
  font-style: italic;
  letter-spacing: 0.02em;
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
