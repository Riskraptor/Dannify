<template>
  <section>
    <h2 class="group-title">{{ t('spotify.title') }}</h2>
    <div class="row">
      <span class="row-brand is-spotify" aria-hidden="true">
        <img v-if="me.image && !photoFailed" :src="me.image" alt="" referrerpolicy="no-referrer" @error="photoFailed = true" />
        <Icon v-else icon="ph:spotify-logo-fill" class="h-6 w-6" />
      </span>
      <div class="row-text">
        <p class="row-label">{{ s.connected ? me.name || t('spotify.title') : t('spotify.title') }}</p>
        <p class="row-hint" :class="{ 'sp-problem': problem }">{{ hint }}</p>
      </div>
      <div class="flex shrink-0 gap-2">
        <template v-if="s.connected">
          <button class="btn" @click="router.push({ name: 'Spotify' })">{{ t('spotify.open') }}</button>
          <button class="btn" @click="spotify.disconnect()">{{ t('spotify.disconnect') }}</button>
        </template>
        <button
          v-else
          class="btn-accent btn-pill press px-4"
          :disabled="!s.configured || s.signing_in"
          @click="spotify.connect()"
        >
          <span v-if="s.signing_in" class="spinner h-4 w-4" />
          <Icon v-else icon="ph:spotify-logo-fill" class="h-4 w-4" />
          {{ s.signing_in ? t('spotify.waiting') : t('spotify.connect') }}
        </button>
      </div>
    </div>
    <!-- Spotify lets an app like this sign in only the few people its owner
         lists. Anyone else can bring a Spotify app of their own. -->
    <div class="row">
      <Icon icon="ph:key" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('spotify.ownApp') }}</p>
        <p class="row-hint">{{ s.own_app ? t('spotify.ownAppOn') : t('spotify.ownAppHint') }}</p>
      </div>
      <div class="flex shrink-0 gap-2">
        <button v-if="s.own_app" class="btn" @click="clearOwnApp">{{ t('spotify.ownAppRemove') }}</button>
        <button class="btn" @click="setOwnApp">{{ s.own_app ? t('spotify.ownAppChange') : t('spotify.ownAppSet') }}</button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import { useSpotify, errorKey } from '/src/model/spotify'
import { confirmDialog, promptDialog } from '/src/model/dialog'
import { toast } from '/src/model/toast'
import { useI18n } from '/src/i18n'

// Spotify in Settings, Accounts: connecting and disconnecting, and one's own
// Spotify app for anyone the app's list does not include.
const { t } = useI18n()
const router = useRouter()
const spotify = useSpotify()
const s = computed(() => spotify.status.value)
const me = computed(() => spotify.user.value)
const photoFailed = ref(false)
onMounted(() => spotify.refresh())

const problem = computed(() => !s.value.connected && !!s.value.error && s.value.error !== 'denied')
const hint = computed(() => {
  if (s.value.connected) return t('spotify.connectedHint')
  if (s.value.signing_in) return t('spotify.waitingHint')
  if (!s.value.configured) return t('spotify.notConfiguredHint')
  if (problem.value) return t(errorKey(s.value.error))
  return t('spotify.hint')
})

async function setOwnApp() {
  const id = await promptDialog({
    title: t('spotify.ownAppTitle'),
    message: t('spotify.ownAppSteps'),
    label: t('spotify.clientId'),
    confirmText: t('spotify.ownAppSave'),
    icon: 'ph:key',
    maxLength: 64,
  })
  if (id == null || !String(id).trim()) return
  try {
    await spotify.setApp(String(id).trim())
    toast(t('spotify.ownAppSaved'), { icon: 'ph:check-circle', tone: 'success' })
  } catch {
    toast(t('spotify.clientIdInvalid'), { tone: 'error', timeout: 7000 })
  }
}

async function clearOwnApp() {
  const ok = await confirmDialog({
    title: t('spotify.ownAppRemove'),
    message: t('spotify.ownAppRemoveText'),
    confirmText: t('spotify.ownAppRemove'),
    icon: 'ph:key',
  })
  if (!ok) return
  try {
    await spotify.setApp('')
  } catch {
    toast(t('spotify.errorFailed'), { tone: 'error' })
  }
}
</script>

<style scoped>
.sp-problem {
  color: rgb(var(--c-warn));
}
</style>
