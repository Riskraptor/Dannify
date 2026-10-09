<template>
  <!-- The mixer, from the player bar: everything about the sound, with no
       need to go into Settings. -->
  <Teleport to="body">
    <div v-if="open" class="snd-layer" @mousedown.self="close" @contextmenu.prevent.self="close">
      <div ref="box" class="snd menu-surface" role="dialog" :aria-label="t('sound.title')" tabindex="-1" :style="place" @keydown="onKey">
        <header class="snd-head">
          <p class="snd-title">{{ t('sound.title') }}</p>
          <div class="seg snd-tabs" role="tablist">
            <button
              v-for="tb in tabs"
              :key="tb.id"
              class="seg-item"
              role="tab"
              :aria-selected="tab === tb.id"
              :class="{ 'is-active': tab === tb.id }"
              @click="setTab(tb.id)"
            >
              <Icon :icon="tb.icon" class="h-4 w-4" />
              {{ t(tb.label) }}
            </button>
          </div>
        </header>

        <!-- Equalizer -->
        <section v-if="tab === 'eq'" class="snd-body">
          <template v-if="engineOn">
            <div class="snd-line">
              <span class="snd-label">{{ t('settings.equalizer') }}</span>
              <input
                type="checkbox"
                class="switch"
                :checked="player.eq.value.on"
                @change="player.setEqEnabled($event.target.checked)"
              />
            </div>
            <EqGraph
              :on="player.eq.value.on"
              :gains="player.eq.value.gains"
              @band="(i, db) => player.setEqBand(i, db)"
            />
            <p class="snd-hint">{{ t('sound.graphHint') }}</p>

            <div class="snd-chips">
              <button
                v-for="name in builtIn"
                :key="name"
                class="snd-chip"
                :class="{ 'is-on': player.eq.value.on && player.eq.value.preset === name }"
                @click="player.setEqPreset(name)"
              >
                {{ t(`settings.eqPreset.${name}`) }}
              </button>
              <button
                v-for="p in player.eqUserPresets.value"
                :key="'u' + p.name"
                class="snd-chip is-mine"
                :class="{ 'is-on': player.eq.value.on && player.eq.value.preset === 'user:' + p.name }"
                :title="t('sound.presetMenuHint')"
                @click="player.setEqPreset('user:' + p.name)"
                @contextmenu.prevent="onPresetMenu($event, p)"
              >
                <Icon icon="ph:star-fill" class="h-3 w-3" />
                {{ p.name }}
              </button>
              <button class="snd-chip is-save" :title="t('sound.savePreset')" @click="savePreset">
                <Icon icon="ph:plus" class="h-3.5 w-3.5" />
                {{ t('sound.save') }}
              </button>
            </div>

            <div class="snd-row">
              <span class="snd-label">
                {{ t('sound.preamp') }}
                <span class="snd-value">{{ preampLabel }}</span>
              </span>
              <div class="snd-pre">
                <button
                  class="snd-mini"
                  :class="{ 'is-on': player.eq.value.preamp === 'auto' }"
                  :title="t('sound.preampAutoHint')"
                  @click="player.setEqPreamp(player.eq.value.preamp === 'auto' ? autoPreamp : 'auto')"
                >
                  {{ t('sound.auto') }}
                </button>
                <RangeSlider
                  class="flex-1"
                  :value="(preampValue + 12) / 24"
                  :step="1 / 48"
                  :label="t('sound.preamp')"
                  :tooltip="(r) => formatDb(r * 24 - 12)"
                  @input="(v) => player.setEqPreamp(v * 24 - 12)"
                />
              </div>
            </div>
          </template>
          <p v-else class="snd-hint">{{ t('sound.noEngine') }}</p>
        </section>

        <!-- Effects: between songs, how loud, how fast -->
        <section v-else-if="tab === 'fx'" class="snd-body">
          <template v-if="engineOn">
            <div class="snd-row">
              <span class="snd-label">
                <Icon icon="ph:intersect" class="h-4 w-4" />{{ t('settings.crossfade') }}
                <span class="snd-value">{{ crossfadeLabel }}</span>
              </span>
              <RangeSlider
                :value="player.crossfade.value / 12"
                :step="1 / 12"
                :label="t('settings.crossfade')"
                :tooltip="(r) => (Math.round(r * 12) ? t('settings.seconds', { n: Math.round(r * 12) }) : t('settings.crossfadeOff'))"
                @input="(v) => player.setCrossfade(Math.round(v * 12))"
              />
            </div>
            <label class="snd-line" :class="{ 'is-dim': player.crossfade.value > 0 }">
              <span class="snd-label"><Icon icon="ph:infinity" class="h-4 w-4" />{{ t('settings.gapless') }}</span>
              <input
                type="checkbox"
                class="switch"
                :disabled="player.crossfade.value > 0"
                :checked="player.gapless.value || player.crossfade.value > 0"
                @change="player.setGapless($event.target.checked)"
              />
            </label>
          </template>

          <label class="snd-line">
            <span class="snd-label"><Icon icon="ph:equalizer" class="h-4 w-4" />{{ t('settings.normalize') }}</span>
            <input
              type="checkbox"
              class="switch"
              :checked="player.normalizeLoudness.value"
              @change="player.setNormalizeLoudness($event.target.checked)"
            />
          </label>
          <div v-if="player.normalizeLoudness.value" class="seg snd-seg">
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

          <div class="snd-row">
            <span class="snd-label">
              <Icon icon="ph:gauge" class="h-4 w-4" />{{ t('sound.speed') }}
              <span class="snd-value">{{ player.speed.value.toFixed(2).replace(/0$/, '') }}×</span>
            </span>
            <div class="snd-chips is-tight">
              <button
                v-for="s in [0.75, 1, 1.25, 1.5]"
                :key="s"
                class="snd-chip"
                :class="{ 'is-on': player.speed.value === s }"
                @click="player.setSpeed(s)"
              >
                {{ s }}×
              </button>
            </div>
            <RangeSlider
              :value="(player.speed.value - 0.5) / 1.5"
              :step="0.05 / 1.5"
              :label="t('sound.speed')"
              :tooltip="(r) => `${(0.5 + r * 1.5).toFixed(2)}×`"
              @input="(v) => player.setSpeed(0.5 + v * 1.5)"
            />
          </div>
          <label class="snd-line">
            <span class="snd-label"><Icon icon="ph:music-note" class="h-4 w-4" />{{ t('sound.keepPitch') }}</span>
            <input
              type="checkbox"
              class="switch"
              :checked="player.keepPitch.value"
              @change="player.setKeepPitch($event.target.checked)"
            />
          </label>
        </section>

        <!-- Space: left and right -->
        <section v-else class="snd-body">
          <template v-if="engineOn">
            <div class="snd-row" @dblclick="player.setBalance(0)">
              <span class="snd-label">
                {{ t('settings.balance') }}
                <span class="snd-value">{{ balanceLabel }}</span>
              </span>
              <div class="bal-wrap">
                <span class="bal-side">{{ t('settings.balanceLeft') }}</span>
                <div class="bal-track">
                  <span class="bal-centre" />
                  <span class="bal-fill" :style="balanceFill" />
                  <input
                    class="bal-input"
                    type="range"
                    min="-1"
                    max="1"
                    step="0.05"
                    :value="player.balance.value"
                    :aria-label="t('settings.balance')"
                    @input="onBalance($event.target.value)"
                  />
                </div>
                <span class="bal-side">{{ t('settings.balanceRight') }}</span>
              </div>
              <div class="bal-ears" aria-hidden="true">
                <span class="bal-ear" :style="{ opacity: 0.3 + 0.7 * Math.min(1, 1 - player.balance.value) }">
                  <Icon icon="ph:speaker-simple-high-fill" class="h-5 w-5 -scale-x-100" />
                </span>
                <span class="bal-ear" :style="{ opacity: 0.3 + 0.7 * Math.min(1, 1 + player.balance.value) }">
                  <Icon icon="ph:speaker-simple-high-fill" class="h-5 w-5" />
                </span>
              </div>
            </div>
            <label class="snd-line">
              <span class="snd-label"><Icon icon="ph:ear" class="h-4 w-4" />{{ t('settings.mono') }}</span>
              <input type="checkbox" class="switch" :checked="player.mono.value" @change="player.setMono($event.target.checked)" />
            </label>
            <p class="snd-hint">{{ t('settings.monoHint') }}</p>
          </template>
          <button v-if="desktop.isDesktop" class="snd-wide" @click="desktop.openSoundSettings()">
            <Icon icon="ph:headphones" class="h-4 w-4" />
            {{ t('settings.outputDevice') }}
            <Icon icon="ph:arrow-square-out" class="ml-auto h-4 w-4 opacity-60" />
          </button>
        </section>

        <footer class="snd-foot">
          <button class="snd-link" @click="resetAll">
            <Icon icon="ph:arrow-counter-clockwise" class="h-3.5 w-3.5" />
            {{ t('sound.resetAll') }}
          </button>
          <button class="snd-link" @click="openSettings">
            {{ t('sound.allSettings') }}
            <Icon icon="ph:caret-right" class="h-3 w-3" />
          </button>
        </footer>
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
import { promptDialog } from '/src/model/dialog'
import { openContextMenu } from '/src/model/contextMenu'
import { desktop } from '/src/desktop/bridge'
import { useI18n } from '/src/i18n'
import RangeSlider from '../ui/RangeSlider.vue'
import EqGraph from '../ui/EqGraph.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  anchor: { type: Object, default: null },
})
const emit = defineEmits(['close'])

const { t } = useI18n()
const router = useRouter()
const player = usePlayer()
const engineOn = computed(() => player.hasEngine())
const builtIn = Object.keys(EQ_PRESETS)
const box = ref(null)
const place = ref({})

const TAB_KEY = 'dn.soundTab'
const tabs = [
  { id: 'eq', label: 'sound.tabEq', icon: 'ph:sliders-horizontal' },
  { id: 'fx', label: 'sound.tabEffects', icon: 'ph:waveform' },
  { id: 'space', label: 'sound.tabSpace', icon: 'ph:speaker-simple-high' },
]
const tab = ref((() => {
  try {
    const v = localStorage.getItem(TAB_KEY)
    return tabs.some((x) => x.id === v) ? v : 'eq'
  } catch {
    return 'eq'
  }
})())
function setTab(id) {
  tab.value = id
  try {
    localStorage.setItem(TAB_KEY, id)
  } catch {
    // this session only
  }
}

const formatDb = (db) => (db > 0 ? `+${db.toFixed(1)} dB` : `${db.toFixed(1)} dB`)
const autoPreamp = computed(() => -Math.max(0, ...player.eq.value.gains.map((g) => Number(g) || 0)) / 2)
const preampValue = computed(() => (player.eq.value.preamp === 'auto' ? autoPreamp.value : player.eq.value.preamp))
const preampLabel = computed(() =>
  player.eq.value.preamp === 'auto' ? `${t('sound.auto')} · ${formatDb(autoPreamp.value)}` : formatDb(preampValue.value)
)
const crossfadeLabel = computed(() =>
  player.crossfade.value ? t('settings.seconds', { n: player.crossfade.value }) : t('settings.crossfadeOff')
)
const balanceLabel = computed(() => {
  const v = Math.round(player.balance.value * 100)
  if (Math.abs(v) < 3) return t('settings.balanceCentre')
  return v < 0 ? `${t('settings.balanceLeft')} ${-v}%` : `${t('settings.balanceRight')} ${v}%`
})
// From the middle out, towards the side that is louder.
const balanceFill = computed(() => {
  const v = player.balance.value
  return v >= 0 ? { left: '50%', width: `${v * 50}%` } : { left: `${50 + v * 50}%`, width: `${-v * 50}%` }
})
function onBalance(v) {
  const n = Number(v)
  player.setBalance(Math.abs(n) < 0.06 ? 0 : n)
}

async function savePreset() {
  const name = await promptDialog({
    title: t('sound.savePreset'),
    label: t('playlists.nameLabel'),
    value: t('sound.myPreset', { n: player.eqUserPresets.value.length + 1 }),
    confirmText: t('playlists.save'),
    icon: 'ph:star',
    maxLength: 40,
  })
  if (name) player.saveEqPreset(name)
}
function onPresetMenu(e, p) {
  openContextMenu(e, [
    { label: t('sound.overwritePreset'), icon: 'ph:floppy-disk', action: () => player.saveEqPreset(p.name) },
    { label: t('sound.deletePreset'), icon: 'ph:trash', danger: true, action: () => player.deleteEqPreset(p.name) },
  ])
}

function resetAll() {
  player.setEqPreset('flat')
  player.setEqPreamp('auto')
  player.setEqEnabled(false)
  player.setCrossfade(0)
  player.setGapless(true)
  player.setVolumeLevel('normal')
  player.setSpeed(1)
  player.setKeepPitch(true)
  player.setBalance(0)
  player.setMono(false)
}

watch(
  () => props.open,
  async (on) => {
    if (!on) return
    await nextTick()
    const r = props.anchor && props.anchor.getBoundingClientRect ? props.anchor.getBoundingClientRect() : null
    const width = Math.min(440, window.innerWidth - 16)
    const right = r ? Math.max(8, window.innerWidth - r.right - 60) : 16
    const bottom = r ? Math.max(8, window.innerHeight - r.top + 10) : 96
    place.value = { right: `${Math.min(right, window.innerWidth - width - 8)}px`, bottom: `${bottom}px`, width: `${width}px` }
    box.value && box.value.focus({ preventScroll: true })
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
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 110px);
  outline: none;
}
.snd-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 14px 16px 10px;
}
.snd-title {
  font-size: 16px;
  font-weight: 700;
}
.snd-tabs .seg-item {
  gap: 5px;
}
.snd-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 16px 10px;
}
.snd-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 0;
}
.snd-line.is-dim {
  opacity: 0.55;
}
.snd-row {
  display: flex;
  flex-direction: column;
  gap: 9px;
  padding: 10px 0;
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
  color: rgb(var(--c-fg) / var(--fg-55));
}
.snd-hint {
  margin: 6px 0 2px;
  font-size: 11.5px;
  line-height: 1.45;
  color: rgb(var(--c-fg) / var(--fg-50));
}
.snd-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
.snd-chips.is-tight {
  margin-top: 0;
}
.snd-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 11px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  background: rgb(var(--c-tint) / 0.07);
  color: rgb(var(--c-fg) / 0.85);
  transition: background-color 0.12s ease;
}
.snd-chip:hover {
  background: rgb(var(--c-tint) / 0.13);
}
.snd-chip.is-on {
  background: rgb(var(--c-fg));
  color: rgb(var(--c-panel));
}
.snd-chip.is-mine :deep(svg) {
  color: rgb(var(--c-accent));
}
.snd-chip.is-on.is-mine :deep(svg) {
  color: inherit;
}
.snd-chip.is-save {
  background: transparent;
  border: 1px dashed rgb(var(--c-tint) / 0.3);
}
.snd-pre {
  display: flex;
  align-items: center;
  gap: 10px;
}
.snd-mini {
  height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 700;
  border: 1px solid rgb(var(--c-tint) / 0.2);
  color: rgb(var(--c-fg) / 0.7);
}
.snd-mini.is-on {
  border-color: rgb(var(--c-accent));
  color: rgb(var(--c-accent));
}
.snd-seg {
  display: flex;
  width: 100%;
  margin-bottom: 6px;
}
.snd-seg .seg-item {
  flex: 1;
  justify-content: center;
}
.bal-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}
.bal-side {
  width: 12px;
  text-align: center;
  font-size: 11px;
  font-weight: 700;
  color: rgb(var(--c-fg) / var(--fg-50));
}
.bal-track {
  position: relative;
  flex: 1;
  height: 6px;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.15);
}
.bal-centre {
  position: absolute;
  top: -5px;
  left: 50%;
  width: 2px;
  height: 16px;
  margin-left: -1px;
  border-radius: 2px;
  background: rgb(var(--c-fg) / 0.35);
}
.bal-fill {
  position: absolute;
  top: 0;
  bottom: 0;
  border-radius: 999px;
  background: rgb(var(--c-accent));
}
.bal-input {
  position: absolute;
  inset: -8px 0;
  width: 100%;
  opacity: 0;
  cursor: pointer;
}
.bal-ears {
  display: flex;
  justify-content: space-between;
  padding: 2px 4px 0;
  color: rgb(var(--c-accent));
}
.bal-ear {
  transition: opacity 0.15s ease;
}
.snd-wide {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  height: 40px;
  margin-top: 10px;
  padding: 0 12px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  background: rgb(var(--c-tint) / 0.06);
}
.snd-wide:hover {
  background: rgb(var(--c-tint) / 0.1);
}
.snd-foot {
  display: flex;
  justify-content: space-between;
  padding: 10px 16px;
  border-top: 1px solid rgb(var(--c-tint) / 0.08);
}
.snd-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--c-fg) / var(--fg-60));
}
.snd-link:hover {
  color: rgb(var(--c-fg));
}
</style>
