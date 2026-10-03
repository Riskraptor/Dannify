<template>
  <!-- The sound, at hand: the equalizer, crossfade, how loud songs are evened
       out to and the balance, without going into Settings. Opens above the
       player bar, from its sound button. -->
  <Teleport to="body">
    <div v-if="open" class="snd-layer" @mousedown.self="close" @contextmenu.prevent.self="close">
      <div ref="box" class="snd menu-surface" role="dialog" :aria-label="t('sound.title')" :style="place" @keydown="onKey">
        <header class="snd-head">
          <p class="snd-title">{{ t('sound.title') }}</p>
          <button class="snd-all" @click="openSettings">
            {{ t('sound.allSettings') }}
            <Icon icon="ph:caret-right" class="h-3 w-3" />
          </button>
        </header>

        <template v-if="engineOn">
          <label class="snd-row">
            <span class="snd-label"><Icon icon="ph:sliders-horizontal" class="h-4 w-4" />{{ t('settings.equalizer') }}</span>
            <input
              type="checkbox"
              class="switch"
              :checked="player.eq.value.on"
              @change="player.setEqEnabled($event.target.checked)"
            />
          </label>
          <div v-if="player.eq.value.on" class="snd-eq">
            <EqCurve class="snd-curve" :on="player.eq.value.on" :gains="player.eq.value.gains" />
            <div class="snd-chips">
              <button
                v-for="name in presets"
                :key="name"
                class="snd-chip"
                :class="{ 'is-on': player.eq.value.preset === name }"
                @click="player.setEqPreset(name)"
              >
                {{ t(`settings.eqPreset.${name}`) }}
              </button>
              <span v-if="player.eq.value.preset === 'custom'" class="snd-chip is-on">
                {{ t('settings.eqPreset.custom') }}
              </span>
            </div>
          </div>

          <div class="snd-row is-stacked">
            <span class="snd-label">
              <Icon icon="ph:intersect" class="h-4 w-4" />{{ t('settings.crossfade') }}
              <span class="snd-value">{{ crossfadeLabel }}</span>
            </span>
            <RangeSlider
              :value="player.crossfade.value / 12"
              :step="1 / 12"
              :label="t('settings.crossfade')"
              @input="(v) => player.setCrossfade(Math.round(v * 12))"
            />
          </div>
        </template>

        <label class="snd-row">
          <span class="snd-label"><Icon icon="ph:equalizer" class="h-4 w-4" />{{ t('settings.normalize') }}</span>
          <input
            type="checkbox"
            class="switch"
            :checked="player.normalizeLoudness.value"
            @change="player.setNormalizeLoudness($event.target.checked)"
          />
        </label>
        <div v-if="player.normalizeLoudness.value" class="snd-seg seg">
          <button
            v-for="level in ['quiet', 'normal', 'loud']"
            :key="level"
            class="seg-item"
            :class="{ 'is-active': player.volumeLevel.value === level }"
            @click="player.setVolumeLevel(level)"
          >
            {{ t(`settings.level.${level}`) }}
          </button>
        </div>

        <div v-if="engineOn" class="snd-row is-stacked" @dblclick="player.setBalance(0)">
          <span class="snd-label">
            <Icon icon="ph:speaker-simple-x" class="h-4 w-4" />{{ t('settings.balance') }}
            <span class="snd-value">{{ balanceLabel }}</span>
          </span>
          <RangeSlider
            :value="(player.balance.value + 1) / 2"
            :step="0.05"
            :label="t('settings.balance')"
            @input="(v) => player.setBalance(Math.abs(v - 0.5) < 0.03 ? 0 : v * 2 - 1)"
          />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import { usePlayer } from '/src/model/player'
import { EQ_PRESETS } from '/src/model/audioEngine'
import { useI18n } from '/src/i18n'
import RangeSlider from '../ui/RangeSlider.vue'
import EqCurve from '../ui/EqCurve.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  // The button it opens from: the panel sits above it.
  anchor: { type: Object, default: null },
})
const emit = defineEmits(['close'])

const { t } = useI18n()
const router = useRouter()
const player = usePlayer()
const engineOn = computed(() => player.hasEngine())
const presets = Object.keys(EQ_PRESETS)
const box = ref(null)
const place = ref({})

const crossfadeLabel = computed(() =>
  player.crossfade.value ? t('settings.seconds', { n: player.crossfade.value }) : t('settings.crossfadeOff')
)
const balanceLabel = computed(() => {
  const v = Math.round(player.balance.value * 100)
  if (Math.abs(v) < 3) return t('settings.balanceCentre')
  return v < 0 ? `${t('settings.balanceLeft')} ${-v}%` : `${t('settings.balanceRight')} ${v}%`
})

watch(
  () => props.open,
  async (on) => {
    if (!on) return
    await nextTick()
    const r = props.anchor && props.anchor.getBoundingClientRect ? props.anchor.getBoundingClientRect() : null
    const width = 340
    const right = r ? Math.max(8, window.innerWidth - r.right - 40) : 16
    const bottom = r ? Math.max(8, window.innerHeight - r.top + 10) : 96
    place.value = { right: `${Math.min(right, window.innerWidth - width - 8)}px`, bottom: `${bottom}px` }
    box.value && box.value.focus && box.value.focus()
  }
)

function close() {
  emit('close')
}
function onKey(e) {
  e.stopPropagation()
  if (e.key === 'Escape') {
    e.preventDefault()
    close()
  }
}
function openSettings() {
  close()
  try {
    localStorage.setItem('dn.settingsPane', 'playback')
  } catch {
    // opens on the pane it was on
  }
  router.push({ name: 'Settings' })
}
</script>

<style scoped>
.snd-layer {
  position: fixed;
  inset: 0;
  z-index: 1050;
}
.snd {
  position: fixed;
  width: 340px;
  max-height: calc(100vh - 120px);
  overflow-y: auto;
  padding: 14px 16px 16px;
  outline: none;
}
.snd-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.snd-title {
  font-size: 15px;
  font-weight: 700;
}
.snd-all {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.6);
}
.snd-all:hover {
  color: rgb(var(--c-fg));
}
.snd-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 0;
}
.snd-row.is-stacked {
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
}
.snd-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  font-weight: 600;
}
.snd-value {
  margin-left: auto;
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--c-fg) / 0.55);
}
.snd-eq {
  padding-bottom: 6px;
}
.snd-curve {
  height: 72px;
  margin-bottom: 8px;
}
.snd-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.snd-chip {
  height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  background: rgb(var(--c-tint) / 0.07);
  color: rgb(var(--c-fg) / 0.85);
}
.snd-chip:hover {
  background: rgb(var(--c-tint) / 0.12);
}
.snd-chip.is-on {
  background: rgb(var(--c-fg));
  color: rgb(var(--c-panel));
}
.snd-seg {
  display: flex;
  width: 100%;
  margin-bottom: 4px;
}
.snd-seg .seg-item {
  flex: 1;
  justify-content: center;
}
</style>
