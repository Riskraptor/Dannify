<template>
  <section class="card" :class="{ 'is-issue': issue }" :aria-label="t('publish.lineOf', { n: index + 1, total })">
    <div class="meta">
      <span class="num">{{ t('publish.lineOf', { n: index + 1, total }) }}</span>
      <span class="stamp" :class="{ 'is-set': line && line.time != null }" data-time>
        <Icon icon="ph:timer-bold" class="h-3.5 w-3.5" />
        {{ line && line.time != null ? formatLrcTime(line.time) : BLANK_STAMP }}
      </span>
      <span v-if="issue" class="pill-danger">{{ t('publish.issueHere') }}</span>
    </div>

    <!-- The line to tap, big enough to read while listening, and the one
         after it, so the next tap is never a surprise. -->
    <p class="text" dir="auto">{{ line && line.text ? line.text : t('publish.emptyLine') }}</p>
    <p class="up-next" dir="auto">
      <template v-if="nextText != null">
        <span class="up-label">{{ t('publish.upNext') }}</span>
        {{ nextText || '♪' }}
      </template>
    </p>

    <div class="card-foot">
      <div class="acts">
        <!-- The one thing this step is about, as a button anyone can find. The
             Space bar does the same from anywhere in the editor. -->
        <button class="tap press" @pointerdown.prevent @click="session.stamp()">
          <Icon icon="ph:hand-tap-bold" class="h-5 w-5" />
          <span>{{ t('publish.tapNow') }}</span>
          <kbd>Space</kbd>
        </button>
        <button v-if="!editor.timed.value" class="btn btn-pill press" @pointerdown.prevent @click="session.playFromStart()">
          <Icon icon="ph:skip-back-fill" class="h-4 w-4" />
          {{ t('publish.fromStart') }}
        </button>
      </div>

      <!-- What can be done to this line. Each row of the list has the same on
           hover; these are here for the keyboard and for narrow windows. -->
      <div class="line-tools" role="group" :aria-label="t('publish.lineTools')">
        <button
          class="icon-btn is-round"
          :disabled="!line || line.time == null"
          :title="t('publish.playFromHere')"
          :aria-label="t('publish.playFromHere')"
          @click="session.playFrom(index)"
        >
          <Icon icon="ph:play-fill" class="h-4 w-4" />
        </button>
        <button
          class="icon-btn is-round"
          :class="{ 'is-on': looping }"
          :title="t('publish.loopLine')"
          :aria-label="t('publish.loopLine')"
          :aria-pressed="looping ? 'true' : 'false'"
          @click="session.toggleLoop(index)"
        >
          <Icon icon="ph:repeat-bold" class="h-4 w-4" />
        </button>
        <button class="icon-btn is-round" :title="t('publish.editText')" :aria-label="t('publish.editText')" @click="editor.startEdit(index)">
          <Icon icon="ph:pencil-simple-bold" class="h-4 w-4" />
        </button>
        <button class="icon-btn is-round" :title="t('publish.addLineBelow')" :aria-label="t('publish.addLineBelow')" @click="session.insertBelow(index)">
          <Icon icon="ph:plus-bold" class="h-4 w-4" />
        </button>
        <button
          class="icon-btn is-round is-danger"
          :disabled="!line"
          :title="t('publish.deleteLine')"
          :aria-label="t('publish.deleteLine')"
          @click="session.remove(index)"
        >
          <Icon icon="ph:x-bold" class="h-4 w-4" />
        </button>
      </div>
    </div>

    <p class="keys">
      <span><kbd class="kbd">←</kbd><kbd class="kbd">→</kbd> {{ t('publish.nudge') }}</span>
      <span><kbd class="kbd">L</kbd> {{ t('publish.loopLine') }}</span>
      <span><kbd class="kbd">Enter</kbd> {{ t('publish.insertBelow') }}</span>
      <span><kbd class="kbd">E</kbd> {{ t('publish.keyEdit') }}</span>
      <span><kbd class="kbd">P</kbd> {{ t('publish.keyPlay') }}</span>
      <span><kbd class="kbd">Z</kbd> {{ t('publish.keyClearLast') }}</span>
    </p>
  </section>
</template>

<script setup>
import { computed, inject } from 'vue'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { LYRICS_EDITOR } from '/src/model/lyrics/useLyricsSubmit'
import { formatLrcTime, BLANK_STAMP } from '/src/model/lyrics/lrc'

const { t } = useI18n()
const { s, session } = inject(LYRICS_EDITOR)
const editor = s.editor

const index = computed(() => editor.active.value)
const total = computed(() => editor.lines.value.length)
const line = computed(() => editor.lines.value[index.value] || null)
const nextText = computed(() => {
  const next = editor.lines.value[index.value + 1]
  return next ? next.text : null
})
const issue = computed(() => !!editor.quality.value[index.value]?.error)
const looping = computed(() => session.loopIndex.value === index.value)
</script>

<style scoped>
.card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid rgb(var(--c-accent) / 0.28);
  background: linear-gradient(135deg, rgb(var(--c-accent) / 0.13), rgb(var(--c-accent) / 0.03));
}
.card.is-issue {
  border-color: rgb(var(--c-danger) / 0.45);
}
.meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 12px;
  font-size: 11.5px;
  font-weight: 700;
}
.num {
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgb(var(--c-accent));
}
.stamp {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--c-fg) / 0.45);
}
.stamp.is-set {
  color: rgb(var(--c-fg) / 0.8);
}
.text {
  /* Three lines' worth, filled or not, so a short line and a long one take
     the same room and the tap button never moves under the pointer. The
     list below always has the whole line. */
  display: -webkit-box;
  height: calc(3 * 1.3em);
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  font-family: var(--font-display, theme('fontFamily.display'));
  font-size: 21px;
  font-weight: 700;
  line-height: 1.3;
  letter-spacing: -0.01em;
  overflow-wrap: anywhere;
  text-align: start;
}
.up-next {
  min-height: 1.45em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  line-height: 1.45;
  color: rgb(var(--c-fg) / 0.5);
}
.up-label {
  margin-inline-end: 6px;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: rgb(var(--c-fg) / 0.4);
}
.card-foot {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 4px;
}
.acts {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.tap {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  height: 44px;
  padding: 0 14px 0 16px;
  border-radius: 999px;
  background: rgb(var(--c-accent));
  color: rgb(var(--c-accent-fg));
  font-size: 14px;
  font-weight: 700;
  box-shadow: 0 6px 18px rgb(var(--c-accent) / 0.28);
  transition: filter 0.12s ease;
}
.tap:hover {
  filter: brightness(1.06);
}
.tap kbd {
  padding: 1px 6px;
  border-radius: 5px;
  background: rgb(0 0 0 / 0.16);
  font-family: inherit;
  font-size: 11px;
  font-weight: 700;
}
.line-tools {
  display: flex;
  gap: 2px;
  padding-top: 8px;
  border-top: 1px solid rgb(var(--c-tint) / 0.08);
}
.icon-btn.is-on {
  background: rgb(var(--c-accent) / 0.16);
  color: rgb(var(--c-accent));
}
.icon-btn.is-danger:hover {
  color: rgb(var(--c-danger));
}
.keys {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  font-size: 11.5px;
  color: rgb(var(--c-fg) / 0.5);
}
.keys span {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.keys .kbd {
  height: 18px;
  min-width: 18px;
  padding: 0 4px;
  font-size: 10.5px;
}
@container editor (max-width: 720px) {
  .text {
    height: calc(2 * 1.3em);
    -webkit-line-clamp: 2;
    font-size: 18px;
  }
  .keys {
    display: none;
  }
  /* One row for the tap and the line's actions: the list below needs the
     height more than the card needs the neatness. */
  .card-foot {
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
  }
  .line-tools {
    padding-top: 0;
    border-top: 0;
  }
  .card {
    padding: 12px 14px;
    gap: 6px;
  }
}
</style>
