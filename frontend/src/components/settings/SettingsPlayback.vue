<template>
  <section>
    <h2 class="group-title">{{ t('settings.playback') }}</h2>
    <label class="row">
      <Icon icon="ph:microphone-stage" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.autoOpenLyrics') }}</p>
        <p class="row-hint">{{ t('settings.autoOpenLyricsHint') }}</p>
      </div>
      <input v-model="ui.autoOpenLyrics.value" type="checkbox" class="switch" />
    </label>
    <label class="row">
      <Icon icon="ph:broadcast" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.autoplayRadio') }}</p>
        <p class="row-hint">{{ t('settings.autoplayRadioHint') }}</p>
      </div>
      <input
        type="checkbox"
        class="switch"
        :checked="player.autoplayRadio.value"
        @change="player.setAutoplayRadio($event.target.checked)"
      />
    </label>
    <label class="row">
      <Icon icon="ph:equalizer" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.normalize') }}</p>
        <p class="row-hint">{{ t('settings.normalizeHint') }}</p>
      </div>
      <input
        type="checkbox"
        class="switch"
        :checked="player.normalizeLoudness.value"
        @change="player.setNormalizeLoudness($event.target.checked)"
      />
    </label>
    <div v-if="player.normalizeLoudness.value" class="row">
      <Icon icon="ph:speaker-simple-high" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.volumeLevel') }}</p>
        <p class="row-hint">{{ t('settings.volumeLevelHint') }}</p>
      </div>
      <div class="seg" role="radiogroup" :aria-label="t('settings.volumeLevel')">
        <button
          v-for="level in ['quiet', 'normal', 'loud']"
          :key="level"
          class="seg-item"
          role="radio"
          :aria-checked="player.volumeLevel.value === level"
          :class="{ 'is-active': player.volumeLevel.value === level }"
          @click="player.setVolumeLevel(level)"
        >
          {{ t(`settings.level.${level}`) }}
        </button>
      </div>
    </div>
    <template v-if="engineOn">
      <div class="row">
        <Icon icon="ph:intersect" class="row-icon" />
        <div class="row-text">
          <p class="row-label">{{ t('settings.crossfade') }}</p>
          <p class="row-hint">{{ t('settings.crossfadeHint') }}</p>
        </div>
        <div class="xf">
          <RangeSlider
            class="xf-slider"
            :value="player.crossfade.value / 12"
            :step="1 / 12"
            :label="t('settings.crossfade')"
            :tooltip="(r) => crossfadeLabel(Math.round(r * 12))"
            @input="(v) => player.setCrossfade(Math.round(v * 12))"
          />
          <span class="xf-value">{{ crossfadeLabel(player.crossfade.value) }}</span>
        </div>
      </div>
      <label class="row" :class="{ 'is-disabled': player.crossfade.value > 0 }">
        <Icon icon="ph:infinity" class="row-icon" />
        <div class="row-text">
          <p class="row-label">{{ t('settings.gapless') }}</p>
          <p class="row-hint">
            {{ player.crossfade.value > 0 ? t('settings.gaplessWithCrossfade') : t('settings.gaplessHint') }}
          </p>
        </div>
        <input
          type="checkbox"
          class="switch"
          :disabled="player.crossfade.value > 0"
          :checked="player.gapless.value || player.crossfade.value > 0"
          @change="player.setGapless($event.target.checked)"
        />
      </label>
      <label class="row">
        <Icon icon="ph:sliders-horizontal" class="row-icon" />
        <div class="row-text">
          <p class="row-label">{{ t('settings.equalizer') }}</p>
          <p class="row-hint">{{ t('settings.equalizerHint') }}</p>
        </div>
        <input
          type="checkbox"
          class="switch"
          :checked="player.eq.value.on"
          @change="player.setEqEnabled($event.target.checked)"
        />
      </label>
      <div v-if="player.eq.value.on" class="row eq">
        <EqGraph
          class="eq-curve"
          :on="player.eq.value.on"
          :gains="player.eq.value.gains"
          @band="(i, db) => player.setEqBand(i, db)"
        />
        <div class="eq-presets" role="radiogroup" :aria-label="t('settings.equalizer')">
          <button
            v-for="name in eqPresetNames"
            :key="name"
            class="eq-chip"
            role="radio"
            :aria-checked="player.eq.value.preset === name"
            :class="{ 'is-active': player.eq.value.preset === name }"
            @click="player.setEqPreset(name)"
          >
            {{ t(`settings.eqPreset.${name}`) }}
          </button>
          <span v-if="player.eq.value.preset === 'custom'" class="eq-chip is-active">
            {{ t('settings.eqPreset.custom') }}
          </span>
          <button
            v-if="player.eq.value.preset !== 'flat'"
            class="eq-chip eq-reset"
            :title="t('settings.eqReset')"
            @click="player.setEqPreset('flat')"
          >
            <Icon icon="ph:arrow-counter-clockwise" class="h-3.5 w-3.5" />
            {{ t('settings.eqReset') }}
          </button>
        </div>
        <div class="eq-bands">
          <label v-for="(hz, i) in EQ_BANDS" :key="hz" class="eq-band">
            <span class="eq-db">{{ formatDb(player.eq.value.gains[i]) }}</span>
            <input
              type="range"
              class="eq-slider"
              min="-12"
              max="12"
              step="0.5"
              :value="player.eq.value.gains[i]"
              :aria-label="`${formatHz(hz)} ${formatDb(player.eq.value.gains[i])}`"
              @input="player.setEqBand(i, $event.target.value)"
            />
            <span class="eq-hz">{{ formatHz(hz) }}</span>
          </label>
        </div>
      </div>
    </template>
    <template v-if="engineOn">
      <div class="row">
        <Icon icon="ph:speaker-simple-x" class="row-icon" />
        <div class="row-text">
          <p class="row-label">{{ t('settings.balance') }}</p>
          <p class="row-hint">{{ t('settings.balanceHint') }}</p>
        </div>
        <div class="xf bal" @dblclick="player.setBalance(0)">
          <span class="bal-side">{{ t('settings.balanceLeft') }}</span>
          <RangeSlider
            class="xf-slider"
            :value="(player.balance.value + 1) / 2"
            :step="0.05"
            :label="t('settings.balance')"
            :tooltip="balanceLabel"
            @input="(v) => player.setBalance(Math.abs(v - 0.5) < 0.03 ? 0 : v * 2 - 1)"
          />
          <span class="bal-side">{{ t('settings.balanceRight') }}</span>
        </div>
      </div>
      <label class="row">
        <Icon icon="ph:ear" class="row-icon" />
        <div class="row-text">
          <p class="row-label">{{ t('settings.mono') }}</p>
          <p class="row-hint">{{ t('settings.monoHint') }}</p>
        </div>
        <input
          type="checkbox"
          class="switch"
          :checked="player.mono.value"
          @change="player.setMono($event.target.checked)"
        />
      </label>
    </template>
    <div v-if="desktop.isDesktop" class="row">
      <Icon icon="ph:headphones" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.outputDevice') }}</p>
        <p class="row-hint">{{ tp('settings.outputDeviceHint') }}</p>
      </div>
      <button class="btn" @click="desktop.openSoundSettings()">
        <Icon icon="ph:arrow-square-out" class="h-4 w-4" />
        {{ t('settings.openSoundSettings') }}
      </button>
    </div>
  </section>
</template>

<script setup>
import { Icon } from '@iconify/vue'
import { useUi } from '/src/model/ui'
import { usePlayer } from '/src/model/player'
import { EQ_BANDS, EQ_PRESETS } from '/src/model/audioEngine'
import { desktop } from '/src/desktop/bridge'
import RangeSlider from '/src/components/ui/RangeSlider.vue'
import EqGraph from '/src/components/ui/EqGraph.vue'
import { useI18n } from '/src/i18n'
import { tp } from '/src/i18n/platform'

const { t } = useI18n()
const ui = useUi()
const player = usePlayer()

// --- The sound engine's settings (see audioEngine.js) ---
const engineOn = player.hasEngine()
const eqPresetNames = Object.keys(EQ_PRESETS)
function crossfadeLabel(seconds) {
  return seconds > 0 ? t('settings.seconds', { count: seconds }) : t('settings.crossfadeOff')
}
function formatDb(db) {
  const v = Number(db) || 0
  return `${v > 0 ? '+' : ''}${v % 1 ? v.toFixed(1) : v} dB`
}
function balanceLabel(r) {
  const v = Math.round((r * 2 - 1) * 100)
  if (Math.abs(v) < 3) return t('settings.balanceCentre')
  return v < 0 ? `${t('settings.balanceLeft')} ${-v}%` : `${t('settings.balanceRight')} ${v}%`
}

function formatHz(hz) {
  return hz >= 1000 ? `${hz / 1000}k` : String(hz)
}
</script>
