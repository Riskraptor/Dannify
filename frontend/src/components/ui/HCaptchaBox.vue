<template>
  <!-- hCaptcha, the check the Web3Forms form asks for, so no robot sends a
       report (see report.py). Invisible: nothing here takes room, and when
       hCaptcha does want a challenge, it shows it in the middle of the
       window rather than hanging off a box near the dialog's foot. -->
  <div class="hcb">
    <div ref="box" class="hcb-box" />
    <p class="hcb-notice">
      <Icon icon="ph:shield-check" class="h-3.5 w-3.5" />
      <span>
        {{ t('problems.captchaNotice') }}
        <button type="button" class="hcb-link" @click="desktop.openExternal('https://www.hcaptcha.com/privacy')">{{ t('problems.captchaPrivacy') }}</button>
        ·
        <button type="button" class="hcb-link" @click="desktop.openExternal('https://www.hcaptcha.com/terms')">{{ t('problems.captchaTerms') }}</button>
      </span>
    </p>
    <p v-if="failed" class="hcb-failed">
      <Icon icon="ph:wifi-slash" class="h-4 w-4" />
      {{ t('problems.captchaOffline') }}
      <button class="hcb-link" type="button" @click="start">{{ t('common.retry') }}</button>
    </p>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Icon } from '@iconify/vue'
import { desktop } from '/src/desktop/bridge'
import { useI18n } from '/src/i18n'

const props = defineProps({ sitekey: { type: String, required: true } })
const { t, locale } = useI18n()

const box = ref(null)
const failed = ref(false)
let widget = null

// The script is fetched once, the first time the check is shown.
let loading = null
function loadScript() {
  if (window.hcaptcha) return Promise.resolve(window.hcaptcha)
  if (loading) return loading
  loading = new Promise((resolve, reject) => {
    const name = `__hcaptchaReady${Date.now()}`
    window[name] = () => resolve(window.hcaptcha)
    const script = document.createElement('script')
    script.src = `https://js.hcaptcha.com/1/api.js?render=explicit&onload=${name}&hl=${encodeURIComponent(locale.value || 'en')}`
    script.async = true
    script.onerror = () => {
      loading = null
      script.remove()
      reject(new Error('hCaptcha did not load'))
    }
    document.head.appendChild(script)
  })
  return loading
}

async function start() {
  failed.value = false
  try {
    const hcaptcha = await loadScript()
    if (!box.value) return
    box.value.innerHTML = ''
    widget = hcaptcha.render(box.value, {
      sitekey: props.sitekey,
      size: 'invisible',
      theme: document.documentElement.dataset.mode === 'light' ? 'light' : 'dark',
    })
  } catch {
    failed.value = true
  }
}

/**
 * The check, when the note reaches the end: a token straight away for most
 * people, after a challenge (in the middle of the window) for some. Rejects
 * when the challenge is closed, or the check cannot load.
 */
async function run() {
  if (widget === null) await start()
  if (widget === null || !window.hcaptcha) throw new Error('hCaptcha is not available')
  const { response } = await window.hcaptcha.execute(widget, { async: true })
  return response
}

/** A token is good for one report: the next send asks again. */
function reset() {
  if (widget !== null && window.hcaptcha) window.hcaptcha.reset(widget)
}
defineExpose({ run, reset })

onMounted(start)
onBeforeUnmount(() => {
  if (widget !== null && window.hcaptcha) {
    try {
      window.hcaptcha.remove(widget)
    } catch {
      // already gone with the dialog
    }
  }
})
</script>

<style scoped>
.hcb {
  display: grid;
  gap: 6px;
  margin-top: 14px;
}
.hcb-box {
  height: 0;
}
.hcb-notice,
.hcb-failed {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 11.5px;
  line-height: 1.45;
  color: rgb(var(--c-fg) / var(--fg-55));
}
.hcb-notice :deep(svg) {
  flex: none;
  margin-top: 1px;
  color: rgb(var(--c-accent));
}
.hcb-failed {
  font-size: 12.5px;
  color: rgb(var(--c-fg) / 0.8);
}
.hcb-link {
  font-weight: 700;
  color: rgb(var(--c-accent));
}
.hcb-link:hover {
  text-decoration: underline;
}
</style>
