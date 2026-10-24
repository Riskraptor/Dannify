<template>
  <section>
    <h2 class="group-title">{{ t('settings.youtubeMusic') }}</h2>

    <!-- Signed in: who, and what the connection brings, said plainly. -->
    <article v-if="account.signedIn.value" class="yt-card">
      <span class="yt-photo" aria-hidden="true">
        <img
          v-if="account.profile.value.photo && !photoFailed"
          :src="account.profile.value.photo"
          alt=""
          referrerpolicy="no-referrer"
          @error="photoFailed = true"
        />
        <Icon v-else icon="ph:user-circle-fill" class="h-8 w-8" />
      </span>
      <div class="yt-who">
        <p class="yt-name">{{ account.displayName.value || t('account.connected') }}</p>
        <p class="yt-state">
          <span class="yt-dot" />
          {{ t('account.connectedTo') }}
        </p>
        <p class="yt-hint">{{ t('account.connectedHint') }}</p>
      </div>
      <button class="btn shrink-0" :disabled="account.busy.value" @click="account.signOut()">
        {{ t('account.signOut') }}
      </button>
    </article>

    <!-- Signed out: what signing in gives, before the button. -->
    <article v-else class="yt-card is-out">
      <span class="yt-photo is-brand" aria-hidden="true">
        <Icon icon="ph:google-logo-bold" class="h-6 w-6" />
      </span>
      <div class="yt-who">
        <p class="yt-name">{{ t('account.signedOutTitle') }}</p>
        <ul class="yt-gains">
          <li><Icon icon="ph:house-line" class="h-4 w-4" />{{ t('account.gainHome') }}</li>
          <li><Icon icon="ph:heart" class="h-4 w-4" />{{ t('account.gainLikes') }}</li>
          <li><Icon icon="ph:chart-bar" class="h-4 w-4" />{{ t('account.gainListening') }}</li>
        </ul>
      </div>
      <button
        class="btn-accent btn-pill press shrink-0 px-4"
        :disabled="account.busy.value || !desktop.isApp"
        @click="account.signIn()"
      >
        <span v-if="account.busy.value" class="spinner h-4 w-4" />
        <Icon v-else icon="ph:google-logo" class="h-4 w-4" />
        {{ account.busy.value ? t('account.connecting') : t('account.connect') }}
      </button>
    </article>

    <template v-if="account.signedIn.value">
      <label class="row">
        <Icon icon="ph:arrow-square-in" class="row-icon" />
        <div class="row-text">
          <p class="row-label">{{ t('account.bringHistory') }}</p>
          <p class="row-hint">{{ t('account.bringHistoryHint') }}</p>
          <!-- How it is going, without a button: it keeps itself up to date. -->
          <p v-if="ytmSyncOn" class="yt-sync">
            <span v-if="ytmSyncing" class="spinner h-3 w-3" />
            <Icon v-else icon="ph:check-circle-fill" class="h-3.5 w-3.5 text-accent" />
            {{ syncLine }}
          </p>
        </div>
        <input type="checkbox" class="switch" :checked="ytmSyncOn" @change="setYtmSync($event.target.checked)" />
      </label>
      <label class="row">
        <Icon icon="ph:arrow-square-out" class="row-icon" />
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
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Icon } from '@iconify/vue'
import { useAccount } from '/src/model/account'
import { desktop } from '/src/desktop/bridge'
import { useI18n } from '/src/i18n'
import { loadYtmStatus, setYtmSync, syncLine as ytmLine, ytmSyncOn, ytmSyncing } from '/src/model/ytmSync'

const { t, locale } = useI18n()
const account = useAccount()
const photoFailed = ref(false)

onMounted(loadYtmStatus)

// "1,234 plays from YouTube Music · up to date 5 minutes ago"
const syncLine = computed(() => ytmLine(t, locale.value))
</script>

<style scoped>
.yt-card {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 10px;
  padding: 18px 20px;
  border-radius: 16px;
  background:
    radial-gradient(90% 140% at 100% 0%, rgb(255 0 51 / 0.12), transparent 60%),
    rgb(var(--c-tint) / 0.045);
  box-shadow: inset 0 0 0 1px rgb(var(--c-tint) / 0.08);
}
.yt-card.is-out {
  align-items: flex-start;
}
.yt-photo {
  display: grid;
  width: 56px;
  height: 56px;
  flex-shrink: 0;
  place-items: center;
  overflow: hidden;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.1);
  color: rgb(var(--c-fg) / 0.7);
}
.yt-photo img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.yt-photo.is-brand {
  background: rgb(var(--c-fg));
  color: rgb(var(--c-elev));
}
.yt-who {
  min-width: 0;
  flex: 1;
}
.yt-name {
  font-size: 16px;
  font-weight: 750;
}
.yt-state {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 2px;
  font-size: 12.5px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.75);
}
.yt-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: rgb(var(--c-accent));
  box-shadow: 0 0 0 3px rgb(var(--c-accent) / 0.2);
}
.yt-hint {
  margin-top: 6px;
  max-width: 62ch;
  font-size: 12.5px;
  line-height: 1.5;
  color: rgb(var(--c-fg) / var(--fg-60, 0.62));
}
.yt-gains {
  display: grid;
  gap: 5px;
  margin-top: 8px;
  font-size: 13px;
  color: rgb(var(--c-fg) / 0.8);
}
.yt-gains li {
  display: flex;
  align-items: center;
  gap: 8px;
}
.yt-gains :deep(svg) {
  color: rgb(var(--c-accent));
}
.yt-sync {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.7);
}
@container (max-width: 560px) {
  .yt-card {
    flex-wrap: wrap;
  }
}
</style>
