<template>
  <header
    ref="bar"
    class="titlebar"
    :class="{
      'is-desktop': desktop.isDesktop,
      'is-inactive': desktop.isDesktop && !win.focused,
      'is-welcome': welcome,
    }"
  >
    <div class="tb-left">
      <button
        v-if="ui.isCompact.value"
        class="icon-btn"
        :title="t('nav.menu')"
        @click="ui.toggleSidebar()"
      >
        <Icon icon="ph:list" class="h-5 w-5" />
      </button>
      <!-- Only when we own the caption. If Windows is drawing its own
           title bar above us, repeating the icon and the name here is what
           makes the app look like it is running inside another app. -->
      <div v-if="!win.nativeFrame" class="tb-brand">
        <img src="../../assets/dannify.svg" alt="" class="h-[18px] w-[18px] drag-none" />
        <span class="tb-name">Dannify</span>
      </div>
      <div class="tb-nav">
        <button
          class="icon-btn"
          :disabled="!nav.back"
          :title="`${t('nav.back')} (Alt+←)`"
          @click="router.back()"
        >
          <Icon icon="ph:caret-left" class="h-[18px] w-[18px]" />
        </button>
        <button
          class="icon-btn"
          :disabled="!nav.forward"
          :title="`${t('nav.forward')} (Alt+→)`"
          @click="router.forward()"
        >
          <Icon icon="ph:caret-right" class="h-[18px] w-[18px]" />
        </button>
      </div>
    </div>

    <div class="tb-center">
      <SearchBox />
    </div>

    <div class="tb-right">
      <div class="tb-app">
        <RepairIndicator />
        <DownloadIndicator />
        <UpdateButton />
        <button
          class="tb-account"
          :class="{ 'is-in': account.signedIn.value }"
          :title="account.signedIn.value ? account.displayName.value : t('account.connect')"
          @click="openAccountMenu"
        >
          <img
            v-if="account.profile.value.photo && !photoFailed"
            :src="account.profile.value.photo"
            alt=""
            class="tb-avatar drag-none"
            referrerpolicy="no-referrer"
            @error="photoFailed = true"
          />
          <span v-else-if="account.signedIn.value" class="tb-avatar tb-initials">
            {{ initials }}
          </span>
          <Icon v-else icon="ph:user-circle" class="h-[19px] w-[19px]" />
          <!-- Signed out: the same button, saying what it does. Home used to
               carry a second "Sign in" button of its own for this. -->
          <span v-if="!account.signedIn.value && desktop.isDesktop && !ui.isCompact.value" class="tb-signin">
            {{ t('account.connect') }}
          </span>
        </button>
        <!-- Settings lives at the foot of the sidebar. Only when the sidebar
             is a closed drawer (phone-sized windows) is it repeated here, or
             it would be two clicks away. Ctrl+, works everywhere. -->
        <button
          v-if="ui.isCompact.value"
          class="icon-btn"
          :class="{ 'is-active': route.name === 'Settings' }"
          :title="`${t('nav.settings')} (Ctrl+,)`"
          @click="router.push({ name: 'Settings' })"
        >
          <Icon icon="ph:gear-six" class="h-[18px] w-[18px]" />
        </button>
      </div>
      <template v-if="desktop.isDesktop && !win.nativeFrame">
        <span class="tb-sep" />
        <WindowControls />
      </template>
    </div>
  </header>
</template>

<script setup>
import { ref, computed, reactive, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Icon } from '@iconify/vue'
import { desktop, bindWindowDrag } from '/src/desktop/bridge'
import { useUi } from '/src/model/ui'
import { useAccount } from '/src/model/account'
import { useHomeFeed } from '/src/model/home'
import { useOnboarding } from '/src/model/onboarding'
import { openContextMenu } from '/src/model/contextMenu'
import { useI18n } from '/src/i18n'
import SearchBox from './SearchBox.vue'
import WindowControls from './WindowControls.vue'
import DownloadIndicator from './DownloadIndicator.vue'
import RepairIndicator from './RepairIndicator.vue'
import UpdateButton from './UpdateButton.vue'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const ui = useUi()
const account = useAccount()
const welcome = useOnboarding().show
const win = desktop.state

const bar = ref(null)
const nav = reactive({ back: false, forward: false })
const photoFailed = ref(false)

const initials = computed(() =>
  (account.displayName.value || '?')
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase()
)

function openAccountMenu(e) {
  if (!account.signedIn.value) {
    if (!account.busy.value) account.signIn()
    return
  }
  openContextMenu(
    e,
    [
      { label: account.displayName.value, icon: 'ph:user-circle', disabled: true },
      { divider: true },
      {
        label: t('account.likedSongs'),
        icon: 'ph:heart',
        action: () => router.push({ name: 'Liked' }),
      },
      {
        label: t('account.refreshFeed'),
        icon: 'ph:arrows-clockwise',
        // The recommendations are the home feed. This used to refresh the
        // account alone, and nothing on screen changed.
        action: () => {
          account.refresh()
          useHomeFeed().load(true)
        },
      },
      { divider: true },
      { label: t('account.signOut'), icon: 'ph:sign-out', action: () => account.signOut() },
    ],
    { anchor: true }
  )
}

function syncNav() {
  const s = window.history.state || {}
  nav.back = !!s.back
  nav.forward = !!s.forward
}

let unbindDrag = () => {}
let removeHook = () => {}
onMounted(() => {
  unbindDrag = bindWindowDrag(bar.value)
  removeHook = router.afterEach(() => requestAnimationFrame(syncNav))
  syncNav()
})
onBeforeUnmount(() => {
  unbindDrag()
  removeHook()
})
</script>

<style scoped>
.titlebar {
  display: grid;
  /* The sides take what they need and the search box takes the rest. It used
     to be the other way round — a 220 px floor under the search box — and in
     a small window that floor pushed the account and settings buttons out
     from under it, so they sat on top of the field. */
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  height: var(--titlebar-h);
  padding-left: 12px;
  background: rgb(var(--c-app));
}
.titlebar:not(.is-desktop) {
  padding-right: 12px;
}
.tb-left,
.tb-right {
  display: flex;
  align-items: center;
  min-width: 0;
  height: 100%;
}
.tb-left {
  gap: 10px;
}
.tb-right {
  justify-content: flex-end;
  gap: 4px;
}
.tb-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-right: 4px;
  pointer-events: none;
}
.tb-name {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: rgb(var(--c-fg) / 0.85);
}
.tb-nav {
  display: flex;
  gap: 2px;
}
.tb-center {
  display: flex;
  justify-content: center;
  min-width: 0;
}
.tb-center > * {
  width: min(100%, 480px);
  min-width: 0;
}
/* Very narrow: the name goes before anything that can be clicked does. */
@media (max-width: 820px) {
  .titlebar {
    gap: 8px;
  }
  .tb-name {
    display: none;
  }
}
.tb-account {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  border-radius: 999px;
  color: rgb(var(--c-fg) / 0.7);
  transition:
    background-color 0.12s ease,
    color 0.12s ease;
}
.tb-account:hover {
  background: rgb(var(--c-tint) / 0.1);
  color: rgb(var(--c-fg));
}
.tb-account.is-in {
  box-shadow: 0 0 0 1.5px rgb(var(--c-accent) / 0.75);
}
/* Signed out on the desktop: a pill with words rather than a bare icon. */
.tb-account:has(.tb-signin) {
  display: inline-flex;
  width: auto;
  gap: 6px;
  padding: 0 10px 0 6px;
  border: 1px solid rgb(var(--c-tint) / 0.16);
}
.tb-signin {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
.tb-avatar {
  width: 22px;
  height: 22px;
  border-radius: 999px;
  object-fit: cover;
}
.tb-initials {
  display: grid;
  place-items: center;
  background: rgb(var(--c-accent));
  color: rgb(var(--c-accent-fg));
  font-size: 10px;
  font-weight: 700;
}
.tb-sep {
  width: 1px;
  height: 16px;
  margin: 0 6px 0 8px;
  background: rgb(var(--c-tint) / 0.12);
}
.titlebar.is-inactive .tb-brand,
.titlebar.is-inactive .tb-nav {
  opacity: 0.55;
}
.tb-app {
  display: flex;
  align-items: center;
  gap: 4px;
}
/* While the first-run welcome covers the app, only the name and the window
   buttons stay: everything else here would act on the app out of sight. */
.tb-brand,
.tb-nav,
.tb-center,
.tb-app {
  /* Visible at once when coming back, so the search box can take focus the
     moment the welcome closes. */
  transition:
    opacity 0.3s ease,
    visibility 0s;
}
.titlebar.is-welcome .tb-left > .icon-btn,
.titlebar.is-welcome .tb-nav,
.titlebar.is-welcome .tb-center,
.titlebar.is-welcome .tb-app,
.titlebar.is-welcome .tb-sep {
  opacity: 0;
  visibility: hidden;
  transition:
    opacity 0.3s ease,
    visibility 0s 0.3s;
}
@media (max-width: 700px) {
  .titlebar {
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: 8px;
  }
  .tb-name,
  .tb-nav {
    display: none;
  }
}
</style>
