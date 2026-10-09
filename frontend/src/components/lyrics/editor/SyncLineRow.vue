<template>
  <li
    ref="rowEl"
    class="row"
    :class="{ active, timed, error: q.error, warn: q.warn, editing }"
    :data-index="index"
    :tabindex="active ? 0 : -1"
    :aria-current="active ? 'true' : undefined"
    @click="session.select(index)"
  >
    <span class="num" aria-hidden="true">{{ index + 1 }}</span>
    <!-- Mouse shortcuts: everything here is also on the card above and on
         the keyboard, so none of it is a tab stop of its own. -->
    <button
      class="stamp"
      tabindex="-1"
      data-time
      :title="t('publish.stampLine')"
      @pointerdown.prevent
      @click.stop="session.stamp(index)"
    >
      <Icon :icon="timed ? 'ph:timer-fill' : 'ph:timer-bold'" class="h-3.5 w-3.5 shrink-0" />
      <span>{{ timed ? formatLrcTime(line.time) : BLANK_STAMP }}</span>
    </button>

    <textarea
      v-if="editing"
      v-focus
      class="edit"
      rows="1"
      dir="auto"
      :value="line.text"
      :aria-label="t('publish.editText')"
      @input="onInput"
      @keydown.enter.prevent="finish"
      @keydown.esc.prevent.stop="cancel"
      @blur="onBlur"
      @click.stop
    ></textarea>
    <span v-else class="text" :class="{ 'is-break': !line.text }" dir="auto" @dblclick.stop="editor.startEdit(index)">
      {{ line.text || '♪' }}
    </span>

    <div class="acts">
      <button
        class="act"
        tabindex="-1"
        :disabled="!timed"
        :title="t('publish.playFromHere')"
        @click.stop="session.playFrom(index)"
      >
        <Icon icon="ph:play-fill" class="h-3.5 w-3.5" />
      </button>
      <button class="act" :class="{ on: looping }" tabindex="-1" :title="t('publish.loopLine')" @click.stop="session.toggleLoop(index)">
        <Icon icon="ph:repeat-bold" class="h-3.5 w-3.5" />
      </button>
      <button class="act" tabindex="-1" :title="t('publish.editText')" @click.stop="editor.startEdit(index)">
        <Icon icon="ph:pencil-simple-bold" class="h-3.5 w-3.5" />
      </button>
      <button class="act" tabindex="-1" :title="t('publish.addLineBelow')" @click.stop="session.insertBelow(index)">
        <Icon icon="ph:plus-bold" class="h-3.5 w-3.5" />
      </button>
      <button class="act is-danger" tabindex="-1" :title="t('publish.deleteLine')" @click.stop="session.remove(index)">
        <Icon icon="ph:x-bold" class="h-3.5 w-3.5" />
      </button>
    </div>
  </li>
</template>

<script setup>
import { ref, computed, inject, nextTick } from 'vue'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { LYRICS_EDITOR } from '/src/model/lyrics/useLyricsSubmit'
import { formatLrcTime, BLANK_STAMP } from '/src/model/lyrics/lrc'

const props = defineProps({
  line: { type: Object, required: true },
  index: { type: Number, required: true },
})

const { t } = useI18n()
const { s, session } = inject(LYRICS_EDITOR)
const editor = s.editor

const rowEl = ref(null)
const active = computed(() => editor.active.value === props.index)
const editing = computed(() => editor.editing.value === props.index)
const timed = computed(() => props.line.time != null)
const q = computed(() => editor.quality.value[props.index] || {})
const looping = computed(() => session.loopIndex.value === props.index)

// Typing opens with the caret at the end of the words.
const vFocus = {
  mounted(el) {
    el.focus({ preventScroll: true })
    el.setSelectionRange(el.value.length, el.value.length)
  },
}

// One line is one line: a pasted line break would become a second lyric
// line hidden inside this one.
function onInput(e) {
  const text = e.target.value
  editor.setText(props.index, text.includes('\n') ? text.replace(/\s*\n\s*/g, ' ') : text)
}

function backToRow() {
  nextTick(() => rowEl.value?.focus({ preventScroll: true }))
}

function finish() {
  editor.stopEdit()
  backToRow()
}

function cancel() {
  editor.cancelEdit()
  backToRow()
}

// Clicking elsewhere keeps what was typed. Only this line's edit: the one
// just opened on another line must not be closed by this one's blur.
function onBlur() {
  if (editor.editing.value === props.index) editor.stopEdit()
}
</script>

<style scoped>
.row {
  display: grid;
  grid-template-columns: 2rem auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  min-height: 40px;
  padding: 4px 6px 4px 4px;
  border-radius: 9px;
  border: 1px solid transparent;
  cursor: default;
  transition:
    background-color 0.12s ease,
    border-color 0.12s ease;
}
.row:hover {
  background: rgb(var(--c-tint) / 0.04);
}
.row.active {
  background: rgb(var(--c-accent) / 0.1);
  border-color: rgb(var(--c-accent) / 0.32);
}
.row.error {
  border-color: rgb(var(--c-danger) / 0.4);
}
.row.active.error {
  background: rgb(var(--c-danger) / 0.08);
}
.row:focus-visible {
  outline-offset: 0;
}
.num {
  text-align: end;
  font-size: 11.5px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--c-fg) / 0.35);
}
.row.active .num {
  color: rgb(var(--c-accent));
}
.stamp {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 8px;
  border-radius: 7px;
  border: 1px dashed rgb(var(--c-tint) / 0.2);
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--c-fg) / 0.4);
  transition:
    background-color 0.12s ease,
    color 0.12s ease;
}
.stamp:hover {
  background: rgb(var(--c-accent) / 0.12);
  color: rgb(var(--c-fg));
}
.row.timed .stamp {
  border-style: solid;
  border-color: transparent;
  background: rgb(var(--c-tint) / 0.06);
  color: rgb(var(--c-fg) / 0.85);
}
.row.warn .stamp {
  background: rgb(var(--c-warn) / 0.16);
  color: rgb(var(--c-warn));
}
.row.error .stamp {
  background: rgb(var(--c-danger) / 0.16);
  color: rgb(var(--c-danger));
}
.text,
.edit {
  font-size: 14px;
  line-height: 1.45;
  overflow-wrap: anywhere;
  text-align: start;
}
.text {
  padding: 4px 0;
  color: rgb(var(--c-fg) / 0.85);
}
.text.is-break {
  color: rgb(var(--c-fg) / 0.35);
}
.row.active .text {
  color: rgb(var(--c-fg));
  font-weight: 600;
}
/* Grows with what is typed, at the size of the text it replaces, so
   opening a line for typing does not move the rows under it. */
.edit {
  width: 100%;
  min-height: 30px;
  margin: -1px 0;
  padding: 3px 8px;
  resize: none;
  field-sizing: content;
  border-radius: 6px;
  border: 1px solid rgb(var(--c-accent) / 0.7);
  background: rgb(var(--c-elev));
  color: rgb(var(--c-fg));
  outline: none;
}
.acts {
  display: flex;
  gap: 1px;
  opacity: 0;
  transition: opacity 0.12s ease;
}
.row:hover .acts,
.row.active .acts {
  opacity: 1;
}
.act {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 6px;
  color: rgb(var(--c-fg) / 0.6);
}
.act:hover:not(:disabled) {
  background: rgb(var(--c-tint) / 0.1);
  color: rgb(var(--c-fg));
}
.act:disabled {
  opacity: 0.3;
}
.act.on {
  background: rgb(var(--c-accent) / 0.16);
  color: rgb(var(--c-accent));
}
.act.is-danger:hover {
  color: rgb(var(--c-danger));
}
/* Narrow: the words get the room; the card above has the line's actions. */
@container editor (max-width: 720px) {
  .row {
    grid-template-columns: 1.6rem auto minmax(0, 1fr);
    gap: 8px;
  }
  .acts {
    display: none;
  }
}
</style>
