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
    </template>
  </section>
</template>

<script setup>
import { Icon } from '@iconify/vue'
import { useUi } from '/src/model/ui'
import { usePlayer } from '/src/model/player'
import RangeSlider from '/src/components/ui/RangeSlider.vue'
import { useI18n } from '/src/i18n'

// How the music plays: from one song into the next. How it sounds is in
// SettingsSound.vue.
const { t } = useI18n()
const ui = useUi()
const player = usePlayer()

const engineOn = player.hasEngine()
function crossfadeLabel(seconds) {
  return seconds > 0 ? t('settings.seconds', { count: seconds }) : t('settings.crossfadeOff')
}
</script>
