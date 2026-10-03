<template>
  <!-- Following an artist on YouTube Music: they show in Your Library, and
       their new music in YouTube Music's own suggestions. -->
  <button
    v-if="channelId && account.signedIn.value"
    class="follow-btn press"
    :class="{ 'is-on': on }"
    :title="on ? t('account.unfollowHint') : t('account.followHint')"
    @click="account.toggleFollow({ channel_id: channelId, browse_id: browseId, name, cover_url: cover })"
  >
    <Icon :icon="on ? 'ph:check-bold' : 'ph:user-plus'" class="h-4 w-4" />
    {{ on ? t('account.following') : t('account.follow') }}
  </button>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import { useAccount } from '/src/model/account'
import { useI18n } from '/src/i18n'

const props = defineProps({
  channelId: { type: String, default: '' },
  // The artist's page, when it is not the channel: the followed list holds
  // this one.
  browseId: { type: String, default: '' },
  name: { type: String, default: '' },
  cover: { type: String, default: '' },
})

const { t } = useI18n()
const account = useAccount()
const on = computed(() => account.isFollowing(props.channelId, props.browseId))
</script>

<style scoped>
.follow-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 16px;
  border-radius: 999px;
  border: 1px solid rgb(var(--c-fg) / 0.35);
  font-size: 13px;
  font-weight: 700;
  color: rgb(var(--c-fg));
  transition:
    border-color 0.12s ease,
    transform 0.12s ease;
}
.follow-btn:hover {
  border-color: rgb(var(--c-fg));
  transform: scale(1.03);
}
.follow-btn.is-on {
  border-color: rgb(var(--c-accent) / 0.6);
  color: rgb(var(--c-accent));
}
</style>
