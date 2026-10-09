<template>
  <div ref="listEl" class="list">
    <button class="insert is-top" tabindex="-1" @click="session.insertBelow(-1)">
      <Icon icon="ph:plus-bold" class="h-3.5 w-3.5" />
      <span>{{ t('publish.addLineHere') }}</span>
    </button>
    <ol class="rows" :aria-label="t('publish.linesLabel')">
      <template v-for="(line, idx) in editor.lines.value" :key="line._id">
        <SyncLineRow :line="line" :index="idx" />
        <!-- A thin gap between rows that offers a new line on hover. -->
        <li class="gap" aria-hidden="true">
          <button class="insert" tabindex="-1" :title="t('publish.addLineHere')" @click="session.insertBelow(idx)">
            <Icon icon="ph:plus-bold" class="h-3 w-3" />
          </button>
        </li>
      </template>
    </ol>
  </div>
</template>

<script setup>
import { ref, inject, watch, nextTick, onMounted } from 'vue'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { LYRICS_EDITOR } from '/src/model/lyrics/useLyricsSubmit'
import SyncLineRow from './SyncLineRow.vue'

const { t } = useI18n()
const { s, session } = inject(LYRICS_EDITOR)
const editor = s.editor

const listEl = ref(null)

function rowAt(idx) {
  return listEl.value?.querySelector(`.row[data-index="${idx}"]`) || null
}

// The line to tap next, in the middle of the list: a new line among timed
// ones was below the fold with nothing saying where it was.
function centerActive(smooth) {
  const box = listEl.value
  const row = rowAt(editor.active.value)
  if (!box || !row) return
  const top = row.offsetTop - box.clientHeight / 2 + row.offsetHeight / 2
  box.scrollTo({ top: Math.max(0, top), behavior: smooth ? 'smooth' : 'auto' })
}

watch(
  () => session.reveal.value,
  () => nextTick(() => centerActive(true))
)

// The keyboard focus, when it is on a row, stays with the cursor as the
// arrow keys and the song move it, so the focus ring is where the work is.
watch(
  () => editor.active.value,
  (idx) =>
    nextTick(() => {
      const focused = document.activeElement
      if (!focused || !focused.classList?.contains('row') || !listEl.value?.contains(focused)) return
      rowAt(idx)?.focus({ preventScroll: true })
    })
)

onMounted(() => nextTick(() => centerActive(false)))
</script>

<style scoped>
.list {
  position: relative;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 4px 6px 24px 2px;
}
.rows {
  margin: 0;
  padding: 0;
  list-style: none;
}
.gap {
  position: relative;
  height: 6px;
}
.insert {
  position: absolute;
  left: 50%;
  top: 50%;
  display: grid;
  place-items: center;
  width: 22px;
  height: 16px;
  border-radius: 999px;
  background: rgb(var(--c-elev));
  border: 1px solid rgb(var(--c-tint) / 0.15);
  color: rgb(var(--c-fg) / 0.6);
  opacity: 0;
  transform: translate(-50%, -50%);
  transition: opacity 0.12s ease;
  z-index: 1;
}
.gap:hover .insert {
  opacity: 1;
}
.insert:hover {
  border-color: rgb(var(--c-accent) / 0.6);
  color: rgb(var(--c-accent));
}
.insert.is-top {
  position: static;
  display: flex;
  gap: 6px;
  width: 100%;
  height: 30px;
  margin-bottom: 4px;
  border-style: dashed;
  border-radius: 9px;
  background: transparent;
  font-size: 12px;
  font-weight: 600;
  opacity: 1;
  transform: none;
  justify-content: center;
  align-items: center;
}
</style>
