<template>
  <section>
    <h2 class="group-title">{{ t('support.title') }}</h2>

    <!-- Why: one person's free app, said warmly, once. -->
    <p class="sp-lead">
      <span class="sp-heart" aria-hidden="true"><Icon icon="ph:heart-fill" class="h-4 w-4" /></span>
      <span><b>{{ t('support.heroTitle') }}.</b> {{ support.message || t('support.heroText') }}</span>
    </p>

    <!-- GitHub Sponsors, the way to give from anywhere: monthly or one time,
         any amount, by card; GitHub keeps no fee. -->
    <article v-if="support.sponsors_link" class="sp-gh">
      <div class="sp-gh-main">
        <span class="sp-gh-mark"><Icon icon="ph:github-logo-fill" class="h-5 w-5" /> GitHub Sponsors</span>
        <h3 class="sp-gh-title">{{ t('support.sponsorsTitle') }}</h3>
        <p class="sp-gh-text">{{ t('support.sponsorsLead') }}</p>
        <ul class="sp-gh-points">
          <li><Icon icon="ph:check-bold" class="h-3.5 w-3.5" />{{ t('support.sponsorsMonthly') }}</li>
          <li><Icon icon="ph:check-bold" class="h-3.5 w-3.5" />{{ t('support.sponsorsCard') }}</li>
          <li><Icon icon="ph:check-bold" class="h-3.5 w-3.5" />{{ t('support.sponsorsFee') }}</li>
        </ul>
      </div>
      <div class="sp-gh-side">
        <button class="sp-gh-btn press" @click="giveBySponsors()">
          <Icon icon="ph:heart-fill" class="sp-gh-heart h-5 w-5" />
          {{ t('support.sponsorsGive') }}
          <Icon icon="ph:arrow-up-right-bold" class="h-3.5 w-3.5 opacity-70" />
        </button>
        <p class="sp-gh-note"><Icon icon="ph:info" class="h-3.5 w-3.5" />{{ t('support.sponsorsNote') }}</p>
      </div>
    </article>

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
import { onMounted, ref } from 'vue'
import { Icon } from '@iconify/vue'
import { giveBySponsors, refreshSupport, useSupport } from '/src/model/support'
import { useReporting } from '/src/model/problems'
import { useUpdates } from '/src/model/updates'
import { copyText } from '/src/model/clipboard'
import { useI18n } from '/src/i18n'

// Supporting Dannify, on a page of its own: why, GitHub Sponsors (when it is
// set, see support.py), and the ways to help that cost nothing.
const { t } = useI18n()
const { config: support } = useSupport()
const reporting = useReporting()
// The details as they are now: they can change between releases.
onMounted(refreshSupport)
const updates = useUpdates()

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
  animation: sp-beat 2.4s ease-in-out 3;
}
/* GitHub Sponsors: GitHub's own dark, and its pink heart. */
.sp-gh {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px 28px;
  margin-bottom: 14px;
  padding: 24px;
  border-radius: 18px;
  color: #f0f6fc;
  background:
    radial-gradient(70% 120% at 100% 0%, rgb(219 97 162 / 0.28), transparent 60%),
    linear-gradient(135deg, #161b22, #0d1117);
  box-shadow:
    inset 0 0 0 1px rgb(240 246 252 / 0.1),
    0 16px 36px rgb(0 0 0 / 0.35);
}
.sp-gh-main {
  display: grid;
  justify-items: start;
  gap: 6px;
  min-width: 0;
}
.sp-gh-mark {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px 5px 9px;
  border-radius: 999px;
  background: rgb(240 246 252 / 0.1);
  box-shadow: inset 0 0 0 1px rgb(240 246 252 / 0.15);
  font-size: 13px;
  font-weight: 800;
}
.sp-gh-title {
  margin-top: 6px;
  font-size: 19px;
  font-weight: 800;
  letter-spacing: -0.01em;
}
.sp-gh-text {
  max-width: 56ch;
  font-size: 13.5px;
  line-height: 1.5;
  color: rgb(240 246 252 / 0.82);
}
.sp-gh-points {
  display: grid;
  gap: 4px;
  margin-top: 6px;
  font-size: 13px;
  color: rgb(240 246 252 / 0.9);
}
.sp-gh-points li {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sp-gh-points :deep(svg) {
  color: #3fb950;
}
.sp-gh-side {
  display: grid;
  align-content: center;
  justify-items: stretch;
  gap: 10px;
  min-width: 220px;
}
.sp-gh-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 46px;
  padding: 0 22px;
  border-radius: 999px;
  background: #f0f6fc;
  color: #0d1117;
  font-size: 15px;
  font-weight: 800;
  box-shadow: 0 8px 22px rgb(0 0 0 / 0.3);
  transition:
    transform 0.15s ease,
    filter 0.15s ease;
}
.sp-gh-btn:hover {
  transform: translateY(-1px);
  filter: brightness(1.05);
}
.sp-gh-heart {
  color: #db61a2;
}
.sp-gh-note {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  max-width: 260px;
  font-size: 11.5px;
  line-height: 1.4;
  color: rgb(240 246 252 / 0.7);
}
.sp-gh-note :deep(svg) {
  flex: none;
  margin-top: 1px;
}
@container (max-width: 760px) {
  .sp-gh {
    grid-template-columns: 1fr;
  }
  .sp-gh-side {
    justify-items: start;
    min-width: 0;
  }
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
