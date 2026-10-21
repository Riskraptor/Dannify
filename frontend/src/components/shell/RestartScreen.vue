<template>
  <transition name="brb">
    <div v-if="restarting" class="brb" role="alertdialog" aria-live="assertive" :aria-label="t('brb.title')">
      <div class="brb-stage" aria-hidden="true">
        <!-- A record that keeps turning while the new version goes on. -->
        <div class="brb-record">
          <span class="brb-label"><img src="../../assets/dannify.svg" alt="" class="drag-none" /></span>
        </div>
        <i v-for="n in 5" :key="n" class="brb-note" :style="{ '--n': n }">♪</i>
      </div>
      <h2 class="brb-title">{{ t('brb.title') }}</h2>
      <p class="brb-text">
        {{ restarting.playing && restarting.title ? t('brb.textPlaying', { title: restarting.title }) : t('brb.text') }}
      </p>
      <span class="brb-dots" aria-hidden="true"><i /><i /><i /></span>
    </div>
  </transition>
</template>

<script setup>
import { restarting } from '/src/model/restart'
import { useI18n } from '/src/i18n'

const { t } = useI18n()
</script>

<style scoped>
.brb {
  position: fixed;
  inset: 0;
  z-index: 9000;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 24px;
  text-align: center;
  color: #fff;
  background:
    radial-gradient(60% 50% at 50% 40%, rgb(var(--c-accent) / 0.35), transparent 70%),
    rgb(8 8 10 / 0.92);
  backdrop-filter: blur(14px);
}
.brb-stage {
  position: relative;
  width: 168px;
  height: 168px;
  margin-bottom: 14px;
}
.brb-record {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background:
    radial-gradient(circle, transparent 30%, rgb(255 255 255 / 0.06) 31%, transparent 32%),
    repeating-radial-gradient(circle, #111 0 3px, #1c1c1f 3px 4px);
  box-shadow:
    0 24px 60px rgb(0 0 0 / 0.55),
    inset 0 0 0 2px rgb(255 255 255 / 0.05);
  animation: brb-spin 1.8s linear infinite;
}
/* The shine on the vinyl stays put while the record turns under it. */
.brb-stage::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: conic-gradient(from 210deg, transparent 0 20%, rgb(255 255 255 / 0.12) 25%, transparent 32% 70%, rgb(255 255 255 / 0.08) 75%, transparent 82%);
  pointer-events: none;
}
.brb-label {
  display: grid;
  width: 56px;
  height: 56px;
  place-items: center;
  border-radius: 999px;
  background: rgb(var(--c-accent));
  box-shadow: 0 0 0 3px rgb(0 0 0 / 0.4);
}
.brb-label img {
  width: 30px;
  height: 30px;
}
.brb-note {
  position: absolute;
  bottom: 40%;
  left: 50%;
  font-size: 22px;
  font-style: normal;
  color: rgb(var(--c-accent));
  opacity: 0;
  animation: brb-note 2.4s ease-out infinite;
  animation-delay: calc(var(--n) * 0.45s);
  --x: calc((var(--n) - 3) * 34px);
}
.brb-title {
  font-size: 28px;
  font-weight: 800;
  letter-spacing: -0.02em;
}
.brb-text {
  max-width: 440px;
  font-size: 14.5px;
  line-height: 1.5;
  color: rgb(255 255 255 / 0.8);
}
.brb-dots {
  display: flex;
  gap: 6px;
  margin-top: 10px;
}
.brb-dots i {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: rgb(255 255 255 / 0.8);
  animation: brb-dot 1.1s ease-in-out infinite;
}
.brb-dots i:nth-child(2) {
  animation-delay: 0.15s;
}
.brb-dots i:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes brb-spin {
  to {
    transform: rotate(360deg);
  }
}
@keyframes brb-note {
  0% {
    opacity: 0;
    transform: translate(-50%, 0) scale(0.6);
  }
  20% {
    opacity: 1;
  }
  100% {
    opacity: 0;
    transform: translate(calc(-50% + var(--x)), -150px) rotate(18deg) scale(1.1);
  }
}
@keyframes brb-dot {
  0%,
  100% {
    opacity: 0.3;
    transform: translateY(0);
  }
  50% {
    opacity: 1;
    transform: translateY(-4px);
  }
}
.brb-enter-active {
  transition: opacity 0.35s ease;
}
.brb-enter-from {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .brb-record,
  .brb-note,
  .brb-dots i {
    animation: none;
  }
  .brb-note {
    display: none;
  }
}
</style>
