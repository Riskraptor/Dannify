<template>
  <section>
    <h2 class="group-title">{{ t('settings.listenBrainz') }}</h2>
    <div class="row">
      <span class="row-brand is-listenbrainz" aria-hidden="true">
        <Icon icon="ph:broadcast-bold" class="h-[18px] w-[18px]" />
      </span>
      <div class="row-text">
        <p class="row-label">
          {{ lb.connected ? (lb.user ? lb.user : t('settings.lbConnectedNoName')) : t('settings.listenBrainz') }}
        </p>
        <p class="row-hint" :class="{ 'lb-problem': lb.error }">{{ lbHint }}</p>
      </div>
      <button v-if="lb.connected" class="btn" :disabled="lbBusy" @click="disconnectLb">
        {{ t('settings.lbDisconnect') }}
      </button>
      <button v-else class="btn" :disabled="lbBusy" @click="connectLb">
        <span v-if="lbBusy" class="spinner h-4 w-4" />
        {{ t('settings.lbConnect') }}
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { useListens } from '/src/model/listens'
import { promptDialog } from '/src/model/dialog'
import { toast } from '/src/model/toast'
import { useI18n } from '/src/i18n'

// ListenBrainz: the listens counted here, sent on to the person's profile
// there (Backend/dannify/scrobble.py). Off until they connect it.
const { t } = useI18n()
const listens = useListens()

const lb = ref({ connected: false, user: '', waiting: 0, error: '' })
const lbBusy = ref(false)
const lbHint = computed(() => {
  const now = lb.value
  if (!now.connected) return t('settings.lbHint')
  if (now.error === 'token') return t('settings.lbTokenStopped')
  let text = now.user ? t('settings.lbConnected', { user: now.user }) : t('settings.lbConnectedNoName')
  if (now.waiting) text += ' ' + t('settings.lbWaiting', { count: now.waiting })
  return text
})

function showLb(data) {
  if (!data || typeof data !== 'object') return
  lb.value = {
    connected: !!data.connected,
    user: data.user || '',
    waiting: data.waiting || 0,
    error: data.error || '',
  }
  listens.setScrobbling(lb.value.connected)
}

async function refreshLb() {
  try {
    showLb((await API.listenBrainzStatus()).data)
  } catch {
    // Settings still opens; the row says what it last knew.
  }
}
onMounted(refreshLb)

async function connectLb() {
  const token = await promptDialog({
    title: t('settings.lbConnectTitle'),
    message: t('settings.lbConnectText'),
    label: t('settings.lbToken'),
    confirmText: t('settings.lbConnect'),
    icon: 'ph:broadcast',
    maxLength: 200,
  })
  if (!token) return
  lbBusy.value = true
  try {
    showLb((await API.connectListenBrainz(token)).data)
    toast(t('settings.lbConnectedToast'), { icon: 'ph:check-circle', tone: 'success' })
  } catch (err) {
    const status = err && err.response && err.response.status
    let key = 'settings.lbFailed'
    if (status === 400) key = 'settings.lbInvalid'
    else if (status === 503 || !status) key = 'settings.lbUnreachable'
    toast(t(key), { tone: 'error', timeout: 8000 })
  } finally {
    lbBusy.value = false
  }
}

async function disconnectLb() {
  lbBusy.value = true
  try {
    showLb((await API.disconnectListenBrainz()).data)
    toast(t('settings.lbDisconnectedToast'), { icon: 'ph:broadcast' })
  } catch {
    toast(t('settings.lbFailed'), { tone: 'error' })
  } finally {
    lbBusy.value = false
  }
}
</script>

<style scoped>
.lb-problem {
  color: rgb(var(--c-warn));
}
</style>
