<template>
  <section>
    <h2 class="group-title">{{ t('account.title') }}</h2>
    <div class="row">
      <img
        v-if="account.profile.value.photo"
        :src="account.profile.value.photo"
        alt=""
        class="row-icon h-9 w-9 rounded-full object-cover"
        referrerpolicy="no-referrer"
      />
      <Icon v-else icon="ph:user-circle" class="row-icon h-9 w-9" />
      <div class="row-text">
        <p class="row-label">
          {{ account.signedIn.value ? account.displayName.value || t('account.connected') : t('account.signedOutTitle') }}
        </p>
        <p class="row-hint">
          {{ account.signedIn.value ? t('account.connectedHint') : t('account.signedOutHint') }}
        </p>
      </div>
      <div class="flex shrink-0 gap-2">
        <button
          v-if="account.signedIn.value"
          class="btn"
          :disabled="account.busy.value"
          @click="account.signOut()"
        >
          {{ t('account.signOut') }}
        </button>
        <button
          v-else
          class="btn-accent btn-pill press px-4"
          :disabled="account.busy.value || !desktop.isDesktop"
          @click="account.signIn()"
        >
          <span v-if="account.busy.value" class="spinner h-4 w-4" />
          <Icon v-else icon="ph:google-logo" class="h-4 w-4" />
          {{ account.busy.value ? t('account.connecting') : t('account.connect') }}
        </button>
      </div>
    </div>
    <label v-if="account.signedIn.value" class="row">
      <Icon icon="ph:clock-counter-clockwise" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('account.sendHistory') }}</p>
        <p class="row-hint">{{ t('account.sendHistoryHint') }}</p>
      </div>
      <input
        type="checkbox"
        class="switch"
        :checked="account.sendHistory.value"
        @change="account.setSendHistory($event.target.checked)"
      />
    </label>
  </section>
</template>

<script setup>
import { Icon } from '@iconify/vue'
import { useAccount } from '/src/model/account'
import { desktop } from '/src/desktop/bridge'
import { useI18n } from '/src/i18n'

const { t } = useI18n()
const account = useAccount()
</script>
