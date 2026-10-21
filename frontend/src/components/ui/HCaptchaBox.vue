<template>
  <!-- hCaptcha, the check the Web3Forms form asks for: a robot cannot send a
       report (see report.py). Its own box, in the app's light or dark. -->
  <div class="hcb">
    <div ref="box" class="hcb-box" />
    <p v-if="failed" class="hcb-failed">
      <Icon icon="ph:wifi-slash" class="h-4 w-4" />
      {{ t('problems.captchaOffline') }}
      <button class="hcb-retry" type="button" @click="start">{{ t('common.retry') }}</button>
    </p>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'

const props = defineProps({ sitekey: { type: String, required: true } })
const emit = defineEmits(['token'])
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
      theme: document.documentElement.dataset.mode === 'light' ? 'light' : 'dark',
      callback: (token) => emit('token', token),
      'expired-callback': () => emit('token', ''),
      'error-callback': () => emit('token', ''),
    })
  } catch {
    failed.value = true
    emit('token', '')
  }
}

/** A token is good for one report: after a send, the box asks again. */
function reset() {
  emit('token', '')
  if (widget !== null && window.hcaptcha) window.hcaptcha.reset(widget)
}
defineExpose({ reset })

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
  justify-items: start;
  gap: 6px;
  margin-top: 16px;
  min-height: 78px;
}
.hcb-failed {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  color: rgb(var(--c-fg) / 0.75);
}
.hcb-retry {
  font-weight: 700;
  color: rgb(var(--c-accent));
}
</style>
