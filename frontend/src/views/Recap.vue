<template>
  <div class="recap" :class="`is-${period}`" tabindex="-1" :style="{ '--hue': `${hue}deg` }" @wheel.passive="onWheel">
    <div class="recap-bg" aria-hidden="true" />
    <div class="recap-glow decor" aria-hidden="true" />
    <!-- The year's own covers, drifting behind the story. -->
    <div v-if="mosaic.length" class="recap-mosaic decor" aria-hidden="true">
      <span v-for="(c, i) in mosaic" :key="i" class="recap-tile" :style="{ '--i': i, backgroundImage: `url('${c}')` }" />
    </div>

    <header class="recap-top">
      <button class="icon-btn recap-btn" :title="t('common.close')" :aria-label="t('common.close')" @click="close">
        <Icon icon="ph:x" class="h-5 w-5" />
      </button>
      <!-- Each slide's bar fills as it plays, like a story; a click on one
           goes straight to it. -->
      <div v-if="slides.length > 1" class="recap-steps">
        <button
          v-for="(s, i) in slides"
          :key="s.id"
          class="recap-step"
          :aria-label="t('recap.page', { n: i + 1, total: slides.length })"
          :aria-current="i === at ? 'step' : undefined"
          @click="jump(i)"
        >
          <span class="recap-step-track">
            <i :style="{ transform: `scaleX(${i < at ? 1 : i > at ? 0 : progress})` }" />
          </span>
        </button>
      </div>
      <!-- The music follows the story: each page plays its own song. -->
      <button
        v-if="songRows.length"
        class="icon-btn recap-btn"
        :class="{ 'is-on': follow }"
        :title="t('recap.followMusic')"
        :aria-label="t('recap.followMusic')"
        :aria-pressed="follow"
        @click="setFollow(!follow)"
      >
        <Icon :icon="follow ? 'ph:music-notes-fill' : 'ph:music-notes'" class="h-4 w-4" />
      </button>
      <button
        v-if="slides.length > 1 && timed"
        class="icon-btn recap-btn"
        :title="paused ? t('recap.resume') : t('recap.pause')"
        :aria-label="paused ? t('recap.resume') : t('recap.pause')"
        @click="paused = !paused"
      >
        <Icon :icon="paused ? 'ph:play-fill' : 'ph:pause-fill'" class="h-4 w-4" />
      </button>
      <select
        v-if="period === 'year' && data && data.years && data.years.length > 1"
        class="recap-year"
        :value="year"
        :aria-label="t('recap.pickYear')"
        @change="router.replace({ name: 'Recap', params: { year: $event.target.value } })"
      >
        <option v-for="y in data.years" :key="y" :value="y">{{ y }}</option>
      </select>
    </header>
    <!-- Today, this week, this month, the year: one story each. -->
    <nav class="recap-periods" :aria-label="t('story.tabs')">
      <button
        v-for="p in PERIODS"
        :key="p"
        class="recap-period"
        :class="{ 'is-on': p === period && !ago }"
        :aria-pressed="p === period && !ago"
        @click="pickPeriod(p)"
      >
        {{ t(`story.period.${p}`) }}
      </button>
      <!-- Yesterday, last week, last month: and back to now. -->
      <button v-if="period !== 'year'" class="recap-period is-back" :aria-pressed="ago > 0" @click="setAgo(ago ? 0 : 1)">
        <Icon :icon="ago ? 'ph:arrow-right-bold' : 'ph:clock-counter-clockwise'" class="h-3.5 w-3.5" />
        {{ ago ? t(`story.period.${period}`) : t(`story.last.${period}`) }}
      </button>
    </nav>

    <div v-if="state === 'loading'" class="recap-center">
      <span class="spinner h-8 w-8" />
    </div>

    <div v-else-if="state === 'error'" class="recap-center">
      <p class="recap-small">{{ t('recap.failed') }}</p>
      <button class="recap-cta" @click="load">{{ t('common.retry') }}</button>
    </div>

    <div v-else-if="!data || !data.plays" class="recap-center">
      <p class="recap-eyebrow">{{ title }}</p>
      <h1 class="recap-big">{{ period === 'year' ? t('recap.emptyTitle') : t(`story.${ago ? 'emptyPast' : 'empty'}.${period}`) }}</h1>
      <p class="recap-small">{{ period === 'year' || ago ? t('recap.emptyText') : t(`story.startNow.${period}`) }}</p>
    </div>

    <template v-else>
      <transition :name="direction > 0 ? 'slide-next' : 'slide-prev'" mode="out-in">
        <section
          :key="slide.id"
          class="recap-slide"
          @pointerdown="hold"
          @pointerup="release"
          @pointercancel="release(null)"
          @pointerleave="release(null)"
        >
          <!-- The start -->
          <template v-if="slide.id === 'intro'">
            <!-- Signed in: the story says hello by name. -->
            <p v-if="firstName" class="recap-hey"><AnimatedName :text="t('story.hey', { name: firstName })" /></p>
            <p class="recap-eyebrow">{{ t('recap.eyebrow') }}</p>
            <h1 class="recap-huge" :class="{ 'is-words': period !== 'year' }">{{ title }}</h1>
            <p class="recap-lead">{{ period === 'year' ? t('recap.intro') : t(`story.${ago ? 'introPast' : 'intro'}.${period}`) }}</p>
            <div class="recap-ctas">
              <button class="recap-cta" @click.stop="go(1)">
                {{ t('recap.start') }} <Icon icon="ph:arrow-right-bold" class="h-4 w-4" />
              </button>
              <button v-if="songRows.length" class="recap-cta is-ghost" @click.stop="startWithMusic">
                <Icon icon="ph:music-notes-fill" class="h-4 w-4" /> {{ t('recap.startWithMusic') }}
              </button>
            </div>
          </template>

          <!-- How the year began -->
          <template v-else-if="slide.id === 'first'">
            <p class="recap-eyebrow">{{ period === 'year' ? t('recap.firstEyebrow') : t(`story.began.${period}`) }}</p>
            <button
              class="recap-cover is-tilted recap-play"
              :class="{ 'is-current': isPlayingRow(firstRow) }"
              :aria-label="t('recap.playSong', { title: firstRow.title })"
              @click="playOne(firstRow)"
            >
              <CoverImage :src="firstRow.cover" radius="lg" :size="260" class="h-full w-full" eager />
              <span class="recap-play-mark"><Icon :icon="isPlayingRow(firstRow) ? 'ph:pause-fill' : 'ph:play-fill'" class="h-7 w-7" /></span>
            </button>
            <h1 class="recap-big">{{ firstRow.title }}</h1>
            <p class="recap-lead">{{ firstRow.artistText }}</p>
            <p class="recap-small">
              {{ period === 'day' ? t('story.firstAt', { time: timeText(data.first.at) }) : t('recap.firstOn', { date: dateText(data.first.at) }) }}
            </p>
          </template>

          <!-- How much -->
          <template v-else-if="slide.id === 'minutes'">
            <p class="recap-eyebrow">{{ t('recap.minutesEyebrow') }}</p>
            <h1 class="recap-huge"><CountUp :value="minutes" :format="number" /></h1>
            <p class="recap-lead">{{ t('recap.minutesUnit') }}</p>
            <p class="recap-small">{{ t('recap.minutesDetail', { plays: number(data.plays), days: data.days }) }}</p>
            <p v-if="comparison" class="recap-pill" :class="comparison.up ? 'is-up' : 'is-down'">
              <Icon :icon="comparison.up ? 'ph:trend-up-bold' : 'ph:trend-down-bold'" class="h-4 w-4" />
              {{ comparison.text }}
            </p>
          </template>

          <!-- The moments worth saying, the strongest first (listens._insights) -->
          <template v-else-if="slide.id === 'moments'">
            <p class="recap-eyebrow">{{ t('story.moments') }}</p>
            <ul class="recap-moments">
              <li v-for="(m, i) in moments" :key="m.kind" class="recap-moment-item" :style="{ '--i': i }">
                <component
                  :is="momentGo(m) ? 'button' : 'div'"
                  class="recap-moment"
                  :class="{ 'is-playable': momentGo(m), 'is-current': momentPlaying(m), 'is-top': i === 0 }"
                  @click="momentGo(m) && momentGo(m)()"
                >
                  <span class="recap-moment-icon"><Icon :icon="momentIcon(m)" class="h-5 w-5" /></span>
                  <span class="recap-moment-text">{{ momentText(m, period, t, { ...words, ago }) }}</span>
                  <Icon v-if="momentGo(m)" :icon="momentPlaying(m) ? 'ph:pause-fill' : 'ph:play-fill'" class="recap-moment-go h-4 w-4" />
                </component>
              </li>
            </ul>
          </template>

          <!-- The artist -->
          <template v-else-if="slide.id === 'artist'">
            <p class="recap-eyebrow">{{ t('recap.topArtist') }}</p>
            <button
              class="recap-portrait recap-play"
              :class="{ 'is-current': artistPlaying(topArtist) }"
              :aria-label="t('recap.playArtist', { artist: topArtist.name })"
              @click="playArtist(topArtist)"
            >
              <CoverImage :src="artistPicture(topArtist, 440)" kind="artist" round :size="220" class="h-full w-full" eager />
              <span class="recap-play-mark"><Icon :icon="artistPlaying(topArtist) ? 'ph:pause-fill' : 'ph:play-fill'" class="h-7 w-7" /></span>
            </button>
            <h1 class="recap-big">{{ topArtist.name }}</h1>
            <p class="recap-lead">{{ t('recap.together', { minutes: number(Math.round(topArtist.seconds / 60)) }) }}</p>
            <p class="recap-pill">{{ t('recap.shareOf', { percent: Math.round(artistShare * 100) }) }}</p>
            <div class="recap-ctas">
              <button class="recap-cta is-ghost" @click="openArtistOf(topArtist)">
                <Icon icon="ph:arrow-up-right-bold" class="h-4 w-4" /> {{ t('recap.openArtist', { artist: topArtist.name }) }}
              </button>
            </div>
          </template>

          <template v-else-if="slide.id === 'artists'">
            <p class="recap-eyebrow">{{ t('recap.topArtists') }}</p>
            <ol class="recap-artists">
              <li v-for="(a, i) in data.top_artists" :key="a.name" class="recap-artist-item" :style="{ '--i': i }">
                <button
                  class="recap-artist"
                  :class="{ 'is-current': artistPlaying(a) }"
                  :aria-label="t('recap.playArtist', { artist: a.name })"
                  @click="playArtist(a)"
                >
                  <span class="recap-rank">{{ i + 1 }}</span>
                  <span class="recap-artist-pic-wrap">
                    <CoverImage :src="artistPicture(a, 160)" kind="artist" round :size="80" class="recap-artist-pic" />
                    <span class="recap-play-mark is-small"><Icon :icon="artistPlaying(a) ? 'ph:pause-fill' : 'ph:play-fill'" class="h-4 w-4" /></span>
                  </span>
                  <span class="recap-row-title">{{ a.name }}</span>
                  <span class="recap-row-sub">{{ t('recap.minutesShort', { minutes: number(Math.round(a.seconds / 60)) }) }}</span>
                </button>
                <button class="recap-mini" :title="t('recap.openArtist', { artist: a.name })" :aria-label="t('recap.openArtist', { artist: a.name })" @click="openArtistOf(a)">
                  <Icon icon="ph:arrow-up-right-bold" class="h-3.5 w-3.5" />
                </button>
              </li>
            </ol>
          </template>

          <!-- The song -->
          <template v-else-if="slide.id === 'song'">
            <p class="recap-eyebrow">{{ period === 'year' ? t('recap.topSong') : t(`story.topSong.${period}`) }}</p>
            <button
              class="recap-cover recap-play"
              :class="{ 'is-current': isPlayingRow(songRows[0]) }"
              :aria-label="t('recap.playSong', { title: songRows[0].title })"
              @click="playAt(0)"
            >
              <CoverImage :src="songRows[0].cover" radius="lg" :size="260" class="h-full w-full" eager />
              <span class="recap-play-mark"><Icon :icon="isPlayingRow(songRows[0]) ? 'ph:pause-fill' : 'ph:play-fill'" class="h-7 w-7" /></span>
            </button>
            <h1 class="recap-big">{{ songRows[0].title }}</h1>
            <p class="recap-lead">{{ songRows[0].artistText }}</p>
            <div class="recap-chips">
              <span class="recap-pill">{{ t('recap.playedTimes', { count: data.top_songs[0].plays }) }}</span>
              <span v-if="data.top_song_more" class="recap-pill">
                {{ t('recap.firstPlayed', { date: isoText(data.top_song_more.first) }) }}
              </span>
              <span v-if="data.top_song_more && data.top_song_more.most_in_a_day > 1" class="recap-pill">
                {{ t('recap.mostInDay', { count: data.top_song_more.most_in_a_day }) }}
              </span>
            </div>
          </template>

          <template v-else-if="slide.id === 'songs'">
            <p class="recap-eyebrow">{{ t('recap.topSongs') }}</p>
            <ol class="recap-list">
              <li v-for="(row, i) in songRows.slice(0, 5)" :key="row.key" :style="{ '--i': i }" class="recap-row-item">
                <button
                  class="recap-row"
                  :class="{ 'is-current': isPlayingRow(row) }"
                  :aria-label="t('recap.playSong', { title: row.title })"
                  @click="playAt(i)"
                >
                  <span class="recap-rank">
                    <span v-if="isPlayingRow(row)" class="recap-eq" :aria-label="t('recap.playing')"><i /><i /><i /></span>
                    <template v-else>{{ i + 1 }}</template>
                  </span>
                  <span class="recap-thumb-wrap">
                    <CoverImage :src="row.cover" radius="sm" :size="56" class="recap-thumb" />
                    <Icon icon="ph:play-fill" class="recap-thumb-play h-5 w-5" />
                  </span>
                  <span class="min-w-0 flex-1">
                    <span class="recap-row-title">{{ row.title }}</span>
                    <span class="recap-row-sub">{{ row.artistText }}</span>
                  </span>
                  <span class="recap-row-count">{{ t('stats.playCount', { count: data.top_songs[i].plays }) }}</span>
                </button>
              </li>
            </ol>
          </template>

          <template v-else-if="slide.id === 'albums'">
            <p class="recap-eyebrow">{{ t('recap.topAlbums') }}</p>
            <div class="recap-albums">
              <button
                v-for="(a, i) in data.top_albums"
                :key="a.name + a.artist"
                class="recap-album"
                :style="{ '--i': i }"
                :aria-label="t('recap.openAlbum', { album: a.name })"
                @click="openAlbum(a)"
              >
                <span class="recap-album-art-wrap">
                  <CoverImage :src="coverURL(a.cover)" kind="album" radius="md" :size="160" class="recap-album-art" />
                  <span class="recap-play-mark is-small"><Icon icon="ph:arrow-up-right-bold" class="h-4 w-4" /></span>
                </span>
                <span class="recap-album-words">
                  <span class="recap-row-title">{{ a.name }}</span>
                  <span class="recap-row-sub">{{ a.artist }}</span>
                </span>
              </button>
            </div>
          </template>

          <!-- Part by part (a year's months, a month's weeks, a week's days, a
               day's mornings and evenings): each part's own favourite -->
          <template v-else-if="slide.id === 'months'">
            <p class="recap-eyebrow">{{ period === 'year' ? t('recap.monthsTitle') : t(`story.partsTitle.${period}`) }}</p>
            <div class="recap-months-grid" :style="{ '--cols': data.parts.length <= 7 ? data.parts.length : 6 }">
              <component
                :is="m ? 'button' : 'div'"
                v-for="(m, i) in data.parts"
                :key="i"
                class="recap-month-tile"
                :class="{ 'is-empty': !m, 'is-current': m && artistPlaying(m) }"
                :style="{ '--i': i }"
                :aria-label="m ? t('recap.playArtist', { artist: m.name }) : undefined"
                @click="m && playArtist(m)"
              >
                <CoverImage v-if="m" :src="coverURL(m.cover)" radius="sm" :size="96" class="recap-month-art" />
                <span v-else class="recap-month-art is-blank"><Icon icon="ph:music-note" class="h-5 w-5" /></span>
                <span class="recap-month-name">{{ partText(i) }}</span>
                <span class="recap-month-who">{{ m ? m.name : '—' }}</span>
              </component>
            </div>
          </template>

          <!-- When: the day's clock and the week -->
          <template v-else-if="slide.id === 'clock'">
            <p class="recap-eyebrow">{{ t('recap.clockTitle') }}</p>
            <div class="recap-clock-wrap">
              <svg class="recap-clock" viewBox="-110 -110 220 220" role="img" :aria-label="t('recap.clockPeak', { hour: peakText })">
                <circle r="44" class="recap-clock-face" />
                <g v-for="(bar, h) in clockBars" :key="h" :transform="`rotate(${h * 15})`">
                  <rect
                    x="-3.5"
                    :y="-(50 + bar)"
                    width="7"
                    :height="Math.max(2, bar)"
                    rx="3.5"
                    class="recap-clock-bar"
                    :class="{ 'is-peak': h === data.peak_hour }"
                    :style="{ '--i': h }"
                  />
                </g>
                <text v-for="h in [0, 6, 12, 18]" :key="'l' + h" :transform="`rotate(${h * 15}) translate(0 -34) rotate(${-h * 15})`" class="recap-clock-label">
                  {{ hourShort(h) }}
                </text>
              </svg>
              <div v-if="period !== 'day'" class="recap-week">
                <div v-for="(d, k) in weekOrder" :key="d" class="recap-week-col" :class="{ 'is-peak': d === peakWeekday }">
                  <span class="recap-week-bar" :style="{ '--h': `${Math.max(6, weekBars[d] * 100)}%`, '--i': k }" />
                  <span class="recap-week-day">{{ weekdayText(d) }}</span>
                </div>
              </div>
            </div>
            <p class="recap-lead">{{ t('recap.clockPeak', { hour: peakText }) }}</p>
            <p v-if="period !== 'day'" class="recap-small">{{ t('recap.dayPeak', { day: weekdayText(peakWeekday, 'long') }) }}</p>
          </template>

          <!-- Habits -->
          <template v-else-if="slide.id === 'habits'">
            <p class="recap-eyebrow">{{ t('recap.habits') }}</p>
            <div class="recap-facts">
              <div v-if="period !== 'day'" class="recap-fact" style="--i: 0">
                <Icon icon="ph:calendar-check" class="recap-fact-icon" />
                <p class="recap-fact-value"><CountUp :value="data.days" :format="number" /></p>
                <p class="recap-fact-label">{{ t('recap.daysListened') }}</p>
              </div>
              <div v-if="period !== 'day'" class="recap-fact" style="--i: 1">
                <Icon icon="ph:flame" class="recap-fact-icon" />
                <p class="recap-fact-value">{{ t('recap.daysValue', { count: data.longest_streak }) }}</p>
                <p class="recap-fact-label">{{ t('recap.streak') }}</p>
              </div>
              <div v-if="data.busiest_day && period !== 'day'" class="recap-fact" style="--i: 2">
                <Icon icon="ph:calendar-star" class="recap-fact-icon" />
                <p class="recap-fact-value">{{ isoText(data.busiest_day.date) }}</p>
                <p class="recap-fact-label">
                  {{ t('recap.busiest', { minutes: number(Math.round(data.busiest_day.seconds / 60)) }) }}
                </p>
              </div>
              <button
                v-if="repeatRow"
                class="recap-fact is-playable"
                :class="{ 'is-current': isPlayingRow(repeatRow) }"
                style="--i: 3"
                :aria-label="t('recap.playSong', { title: repeatRow.title })"
                @click="playOne(repeatRow)"
              >
                <Icon :icon="isPlayingRow(repeatRow) ? 'ph:pause-circle-fill' : 'ph:play-circle-fill'" class="recap-fact-icon" />
                <span class="recap-fact-value recap-fact-song">{{ repeatRow.title }}</span>
                <span class="recap-fact-label">
                  {{ t('recap.repeatFact', { count: data.repeat.plays, date: isoText(data.repeat.date) }) }}
                </span>
              </button>
            </div>
          </template>

          <!-- New to you -->
          <template v-else-if="slide.id === 'discovery'">
            <p class="recap-eyebrow">{{ t('recap.discovery') }}</p>
            <h1 class="recap-huge"><CountUp :value="data.new_artists" :format="number" /></h1>
            <p class="recap-lead">{{ t('recap.newArtists', { count: data.new_artists }) }}</p>
            <div class="recap-months" role="img" :aria-label="period === 'year' ? t('recap.monthsLabel') : t('story.chart')">
              <span
                v-for="(secs, m) in data.chart"
                :key="m"
                class="recap-month"
                :style="{ '--h': `${Math.max(4, (secs / maxMonth) * 100)}%`, '--i': m }"
                :title="period === 'year' ? monthText(m) : undefined"
              />
            </div>
          </template>

          <!-- Who you are as a listener -->
          <template v-else-if="slide.id === 'persona'">
            <p class="recap-eyebrow">{{ t('recap.personaEyebrow') }}</p>
            <span class="recap-persona-mark"><Icon :icon="persona.icon" class="h-14 w-14" /></span>
            <h1 class="recap-big">{{ t(`recap.persona.${persona.id}.name`) }}</h1>
            <p class="recap-lead recap-persona-text">{{ t(`recap.persona.${persona.id}.text`, persona.params) }}</p>
          </template>

          <!-- The year on one card -->
          <template v-else-if="slide.id === 'summary'">
            <article class="recap-card">
              <header class="recap-card-head">
                <span class="recap-card-brand">Dannify</span>
                <span class="recap-card-year">{{ summaryTitle }}</span>
              </header>
              <div class="recap-card-body">
                <div v-if="topArtist" class="recap-card-artist">
                  <CoverImage :src="artistPicture(topArtist, 320)" kind="artist" round :size="140" class="recap-card-pic" />
                  <p class="recap-card-label">{{ t('recap.topArtist') }}</p>
                  <p class="recap-card-name">{{ topArtist.name }}</p>
                </div>
                <div class="recap-card-cols">
                  <div>
                    <p class="recap-card-label">{{ t('recap.topSongs') }}</p>
                    <ol class="recap-card-list">
                      <li v-for="(row, i) in songRows.slice(0, 5)" :key="row.key">
                        <button class="recap-card-item" :class="{ 'is-current': isPlayingRow(row) }" :aria-label="t('recap.playSong', { title: row.title })" @click="playAt(i)">
                          <b>{{ i + 1 }}</b>{{ row.title }}
                        </button>
                      </li>
                    </ol>
                  </div>
                  <div>
                    <p class="recap-card-label">{{ t('recap.topArtists') }}</p>
                    <ol class="recap-card-list">
                      <li v-for="(a, i) in data.top_artists" :key="a.name">
                        <button class="recap-card-item" :class="{ 'is-current': artistPlaying(a) }" :aria-label="t('recap.playArtist', { artist: a.name })" @click="playArtist(a)">
                          <b>{{ i + 1 }}</b>{{ a.name }}
                        </button>
                      </li>
                    </ol>
                  </div>
                </div>
                <div class="recap-card-stats">
                  <div>
                    <p class="recap-card-label">{{ t('recap.minutesLabel') }}</p>
                    <p class="recap-card-num">{{ number(minutes) }}</p>
                  </div>
                  <div>
                    <p class="recap-card-label">{{ t('recap.personaEyebrow') }}</p>
                    <p class="recap-card-num is-text">{{ t(`recap.persona.${persona.id}.name`) }}</p>
                  </div>
                </div>
              </div>
            </article>
            <div class="recap-ctas">
              <button class="recap-cta" :disabled="!songRows.length" @click.stop="playTop">
                <Icon icon="ph:play-fill" class="h-4 w-4" /> {{ t('recap.playTop') }}
              </button>
              <button class="recap-cta is-ghost" :disabled="!songRows.length" @click.stop="saveTop">
                <Icon icon="ph:playlist" class="h-4 w-4" /> {{ t('recap.saveTop') }}
              </button>
              <!-- The card as a picture: to paste into a chat, or keep. -->
              <button
                class="recap-cta is-ghost is-icon"
                :disabled="!!sharing"
                :title="t('recap.shareCopy')"
                :aria-label="t('recap.shareCopy')"
                @click.stop="shareCard('copy')"
              >
                <span v-if="sharing === 'copy'" class="spinner h-4 w-4" />
                <Icon v-else icon="ph:copy" class="h-[18px] w-[18px]" />
              </button>
              <button
                class="recap-cta is-ghost is-icon"
                :disabled="!!sharing"
                :title="t('recap.shareSave')"
                :aria-label="t('recap.shareSave')"
                @click.stop="shareCard('save')"
              >
                <span v-if="sharing === 'save'" class="spinner h-4 w-4" />
                <Icon v-else icon="ph:download-simple" class="h-[18px] w-[18px]" />
              </button>
            </div>
            <p class="recap-small">{{ t('recap.outro') }}</p>
          </template>
        </section>
      </transition>

      <nav class="recap-nav">
        <button class="icon-btn recap-btn" :disabled="at === 0" :aria-label="t('recap.previous')" @click="go(-1)">
          <Icon icon="ph:caret-left-bold" class="h-5 w-5" />
        </button>
        <button class="icon-btn recap-btn" :disabled="at >= slides.length - 1" :aria-label="t('recap.next')" @click="go(1)">
          <Icon icon="ph:caret-right-bold" class="h-5 w-5" />
        </button>
      </nav>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { coverURL, entryRow, usePlaylists } from '/src/model/playlists'
import { useArtistLinks } from '/src/model/artistLinks'
import { isRowCurrent, openArtist, playRows } from '/src/model/tracks'
import { usePlayer } from '/src/model/player'
import { hourText } from '/src/model/statsFormat'
import { listensEpoch } from '/src/model/listens'
import { syncSoon } from '/src/model/ytmSync'
import { personaOf } from '/src/model/recapPersona'
import { PERIODS, momentIcon, momentText } from '/src/model/moments'
import { weekStart } from '/src/model/weekStart'
import { useAccount } from '/src/model/account'
import { toast } from '/src/model/toast'
import { useI18n } from '/src/i18n'
import CoverImage from '/src/components/ui/CoverImage.vue'
import CountUp from '/src/components/ui/CountUp.vue'
import AnimatedName from '/src/components/ui/AnimatedName.vue'

// "Your Soundtrack": today, this week, this month or a year of listening told
// as a story that plays by itself (hold to pause, tap, swipe, scroll or click a
// bar to move), made from the app's own history and what YouTube Music adds to
// it (Backend listens.story). Everything in it plays or opens what it shows.

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

const year = computed(() => Number(route.params.year) || new Date().getFullYear())
// Which stretch: ?period=day|week|month, the year when none is named, and
// ?ago=1 for the one before (yesterday, last week, last month).
const period = computed(() => (PERIODS.includes(route.query.period) ? route.query.period : 'year'))
const ago = computed(() => (period.value === 'year' ? 0 : Math.max(0, Math.min(1, Number(route.query.ago) || 0))))
function pickPeriod(p) {
  if (p === period.value && !ago.value) return
  router.replace(p === 'year' ? { name: 'Recap' } : { name: 'Recap', query: { period: p } })
}
function setAgo(n) {
  router.replace({ name: 'Recap', query: n ? { period: period.value, ago: n } : { period: period.value } })
}
// The day weeks start on where the listener is.
const firstDay = weekStart
const account = useAccount()
// The first name of whoever is signed in to YouTube, for saying hello.
const firstName = computed(() =>
  account.signedIn.value ? String(account.displayName.value || '').trim().split(/\s+/)[0].slice(0, 24) : ''
)
const data = shallowRef(null)
const state = ref('loading')
const at = ref(0)
const direction = ref(1)
let asked = 0

async function load() {
  const mine = ++asked
  if (!data.value) state.value = 'loading'
  try {
    const res = await API.getStory(period.value, period.value === 'year' ? year.value : 0, ago.value, firstDay.value)
    if (mine !== asked) return
    const first = !data.value
    data.value = res.data
    state.value = 'ready'
    // Back from an artist the story opened: where it was.
    if (first && at.value === 0) at.value = Math.min(recalled(), Math.max(0, slides.value.length - 1))
    // New listens that came in while the story is under way leave it where it is.
    if (at.value >= slides.value.length) at.value = 0
  } catch {
    if (mine === asked && !data.value) state.value = 'error'
  }
}
watch([year, period, ago, firstDay], () => {
  data.value = null
  at.value = 0
  load()
}, { immediate: true })
// What was played on YouTube Music comes in as the page opens; the story is
// put together again when it does, unless it is already being watched.
syncSoon()
watch(listensEpoch, () => {
  if (at.value === 0) load()
})

// --- What the story says -------------------------------------------------------
const topArtist = computed(() => (data.value && data.value.top_artists[0]) || null)
const artistLinks = useArtistLinks()
// The artist's own photo where the app knows it, else the cover of their song.
function artistPicture(a, size) {
  return a ? artistLinks.artistPhoto(a.name, size) || coverURL(a.cover) : ''
}
const songRows = computed(() => ((data.value && data.value.top_songs) || []).map(entryRow))
const firstRow = computed(() => (data.value && data.value.first ? entryRow(data.value.first) : null))
const repeatRow = computed(() => (data.value && data.value.repeat ? entryRow(data.value.repeat) : null))
const minutes = computed(() => Math.round(((data.value && data.value.seconds) || 0) / 60))
const maxMonth = computed(() => Math.max(1, ...((data.value && data.value.chart) || [0])))
const artistShare = computed(() =>
  topArtist.value && data.value.seconds ? topArtist.value.seconds / data.value.seconds : 0
)
const comparison = computed(() => {
  const d = data.value
  const before = d && d.before && d.before.seconds
  if (!before || !d.seconds) return null
  const pct = Math.round(((d.seconds - before) / before) * 100)
  if (!pct) return null
  const percent = number(Math.abs(pct))
  if (period.value === 'year') {
    return { up: pct > 0, text: t(pct > 0 ? 'recap.moreThanLast' : 'recap.lessThanLast', { percent, year: year.value - 1 }) }
  }
  // Last week is compared with the week before it.
  const which = ago.value ? (pct > 0 ? 'morePrev' : 'lessPrev') : pct > 0 ? 'more' : 'less'
  return { up: pct > 0, text: t(`story.${which}.${period.value}`, { percent }) }
})
// What the story is of: the year, or today, this week, this month by name.
const startDate = computed(() => {
  const [y, m, d] = String((data.value && data.value.start) || '').split('-').map(Number)
  return y ? new Date(y, m - 1, d) : new Date()
})
const title = computed(() => {
  if (period.value === 'year') return String(year.value)
  if (period.value === 'month') {
    // "octobre", "octubre": a month starts its own page with a capital.
    const name = startDate.value.toLocaleDateString(locale.value || 'en', { month: 'long' })
    return name.charAt(0).toLocaleUpperCase(locale.value || 'en') + name.slice(1)
  }
  return ago.value ? t(`story.last.${period.value}`) : t(`story.period.${period.value}`)
})
const summaryTitle = computed(() => {
  if (period.value === 'year') return t('recap.summaryTitle', { year: year.value })
  return t(`story.${ago.value ? 'summaryPast' : 'summary'}.${period.value}`, { month: title.value })
})
// The moments, but the minutes: the story has a page of its own for those.
const moments = computed(() => ((data.value && data.value.insights) || []).filter((m) => m.kind !== 'minutes').slice(0, 5))
const words = { number: (n) => number(n), dateText: (iso) => isoText(iso) }
// A few covers of the year, behind it all.
const mosaic = computed(() => {
  const d = data.value
  if (!d) return []
  const covers = [...(d.top_albums || []), ...(d.top_songs || [])]
    .map((x) => coverURL(x.cover || x.cover_url || ''))
    .filter(Boolean)
  return [...new Set(covers)].slice(0, 8)
})
const clockBars = computed(() => {
  const hours = (data.value && data.value.hours) || []
  const top = Math.max(1, ...hours)
  return Array.from({ length: 24 }, (_, h) => Math.round(((hours[h] || 0) / top) * 52))
})
const weekBars = computed(() => {
  const days = (data.value && data.value.weekdays) || []
  const top = Math.max(1, ...days)
  return Array.from({ length: 7 }, (_, d) => (days[d] || 0) / top)
})
// The week's days in the order a week runs where the listener is.
const weekOrder = computed(() => Array.from({ length: 7 }, (_, k) => (firstDay.value + k) % 7))
const peakWeekday = computed(() => {
  const days = (data.value && data.value.weekdays) || []
  return days.length ? days.indexOf(Math.max(...days)) : 0
})
const peakText = computed(() => (data.value && data.value.peak_hour != null ? hourText(data.value.peak_hour, locale.value) : ''))
const persona = computed(() => personaOf(data.value, songRows.value))

// --- The slides --------------------------------------------------------------------
const slides = computed(() => {
  const d = data.value
  if (!d || !d.plays) return []
  const out = [{ id: 'intro', ms: Infinity }]
  if (d.first) out.push({ id: 'first' })
  out.push({ id: 'minutes' })
  if (moments.value.length) out.push({ id: 'moments', ms: 4000 + moments.value.length * 1500 })
  if (topArtist.value) out.push({ id: 'artist' })
  if (d.top_artists.length > 1) out.push({ id: 'artists', ms: 8000 })
  if (d.top_songs.length) out.push({ id: 'song' })
  if (d.top_songs.length > 1) out.push({ id: 'songs', ms: 8000 })
  if (d.top_albums.length) out.push({ id: 'albums', ms: 8000 })
  if ((d.parts || []).filter(Boolean).length > 1) out.push({ id: 'months', ms: 9000 })
  if (d.peak_hour != null && d.hours) out.push({ id: 'clock', ms: 8000 })
  if (period.value !== 'day' || d.repeat) out.push({ id: 'habits', ms: 8000 })
  if (d.new_artists) out.push({ id: 'discovery' })
  // Who someone is as a listener takes a year to say.
  if (period.value === 'year') out.push({ id: 'persona' })
  out.push({ id: 'summary', ms: Infinity })
  return out
})
const slide = computed(() => slides.value[Math.min(at.value, slides.value.length - 1)] || { id: 'intro' })
// Each slide in a colour of its own: the background turns as the story goes,
// from where each stretch's own colour starts (Home's tiles share them).
const HUES = [0, -30, 25, 55, 90, 140, 175, 210, 245, 280, 315, 340, 20, 0]
const PERIOD_HUE = { day: 30, week: 190, month: -70, year: 0 }
const hue = computed(() => HUES[at.value % HUES.length] + PERIOD_HUE[period.value])

function go(step) {
  jump(at.value + step)
}
function jump(index) {
  const next = Math.max(0, Math.min(slides.value.length - 1, index))
  if (next === at.value) return
  direction.value = next > at.value ? 1 : -1
  at.value = next
  elapsed.value = 0
}

// --- Playing by itself -------------------------------------------------------------
const STEP_MS = 6500
const paused = ref(false)
const elapsed = ref(0)
let holding = false
let heldAt = 0
let raf = 0
let lastTick = 0
const duration = computed(() => slide.value.ms || STEP_MS)
const timed = computed(() => Number.isFinite(duration.value))
const progress = computed(() => (timed.value ? Math.min(1, elapsed.value / duration.value) : 0))

function ticking() {
  return !paused.value && timed.value && state.value === 'ready'
}
function tick(now) {
  raf = 0
  if (!ticking()) {
    lastTick = 0
    return
  }
  const dt = lastTick ? Math.min(100, now - lastTick) : 0
  lastTick = now
  if (!holding) {
    elapsed.value += dt
    if (elapsed.value >= duration.value) go(1)
  }
  if (!raf) raf = requestAnimationFrame(tick)
}
// Started again whenever a page starts timing: a new page, play after pause.
function wake() {
  if (!raf && ticking()) {
    lastTick = 0
    raf = requestAnimationFrame(tick)
  }
}
watch([paused, timed, state, () => slide.value.id], wake)

// Press and hold pauses; a quick tap steps (the left third back, the rest on);
// a swipe goes the way it was swiped. What can be pressed is left to itself.
let heldX = 0
function hold(e) {
  if (e.button > 0 || (e.target && e.target.closest && e.target.closest('button, a, select, input'))) return
  holding = true
  heldAt = performance.now()
  heldX = e.clientX
}
function release(e) {
  if (!holding) return
  holding = false
  if (!e) return
  const dx = e.clientX - heldX
  if (Math.abs(dx) > 60) return go(dx < 0 ? 1 : -1)
  if (performance.now() - heldAt > 300) return
  const box = e.currentTarget.getBoundingClientRect()
  go(e.clientX - box.left < box.width / 3 ? -1 : 1)
}

// A wheel or a touchpad turns the pages, one per gesture; on a page taller
// than the window it scrolls the page first, and turns it at the end.
let wheeled = 0
function onWheel(e) {
  const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY
  const page = e.target && e.target.closest ? e.target.closest('.recap-slide') : null
  if (page && d === e.deltaY && page.scrollHeight > page.clientHeight + 2) {
    const atEnd = d > 0 ? page.scrollTop + page.clientHeight >= page.scrollHeight - 2 : page.scrollTop <= 0
    if (!atEnd) {
      wheeled = performance.now()
      return
    }
  }
  if (Math.abs(d) < 24 || state.value !== 'ready') return
  const now = performance.now()
  if (now - wheeled < 600) return
  wheeled = now
  go(d > 0 ? 1 : -1)
}

// The arrows step through the story wherever the focus is, ahead of the
// player's own (which would seek the song): the window hears them first, and
// a key handled here is marked so the player leaves it alone.
function onKey(e) {
  if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return
  const el = e.target
  const tag = (el && el.tagName) || ''
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (el && el.isContentEditable)) return
  // Space on a button presses it; anywhere else it steps on.
  const onButton = tag === 'BUTTON' || tag === 'A'
  if (e.key === 'ArrowRight' || (e.key === ' ' && !onButton)) {
    e.preventDefault()
    go(1)
  } else if (e.key === 'ArrowLeft') {
    e.preventDefault()
    go(-1)
  } else if (e.key === 'Home' || e.key === 'End') {
    e.preventDefault()
    jump(e.key === 'Home' ? 0 : slides.value.length - 1)
  } else if (e.key === 'Escape') {
    e.preventDefault()
    close()
  }
}
onMounted(() => {
  window.addEventListener('keydown', onKey, true)
  wake()
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey, true)
  cancelAnimationFrame(raf)
  raf = 0
  if (!closing) remember()
})

// Where the story was, for coming back to it from a page it opened: kept a
// while, and forgotten when it is closed.
const PLACE_KEY = 'dn.recapPlace'
let closing = false
function remember() {
  try {
    sessionStorage.setItem(PLACE_KEY, JSON.stringify({ year: year.value, period: period.value, ago: ago.value, at: at.value, when: Date.now() }))
  } catch {
    // storage blocked: the story starts at its beginning
  }
}
function recalled() {
  try {
    const place = JSON.parse(sessionStorage.getItem(PLACE_KEY) || 'null')
    const same = place && place.year === year.value && (place.period || 'year') === period.value && (place.ago || 0) === ago.value
    if (same && Date.now() - place.when < 30 * 60 * 1000) return place.at || 0
  } catch {
    // nothing kept
  }
  return 0
}

function close() {
  closing = true
  try {
    sessionStorage.removeItem(PLACE_KEY)
  } catch {
    // nothing kept
  }
  if (window.history.length > 1) router.back()
  else router.push({ name: 'Stats' })
}

// --- Playing what it shows ----------------------------------------------------------
const player = usePlayer()
function songId(row) {
  return (row && (row.file || (row.raw && (row.raw.song_id || row.raw.video_id)))) || ''
}
function isPlayingRow(row) {
  return !!row && player.isPlaying.value && isRowCurrent(row)
}
// A song, then the rest of the year's top songs after it.
function playOne(row, { toggle = true } = {}) {
  if (!row) return
  const id = songId(row)
  const at = id ? songRows.value.findIndex((r) => songId(r) === id) : -1
  if (at >= 0) playRows(songRows.value, at, { toggle })
  else playRows([row, ...songRows.value], 0, { toggle })
}
function playAt(index) {
  playRows(songRows.value, index)
}
function playTop() {
  if (songRows.value.length) playRows(songRows.value, 0, { toggle: false })
}
// An artist's songs of the year, as far as the year's top songs go.
function artistRows(a) {
  if (!a || !a.name) return []
  const name = a.name.toLowerCase()
  return songRows.value.filter(
    (r) => (r.artists || []).some((x) => (x.name || '').toLowerCase() === name) || (r.primaryArtist || '').toLowerCase() === name
  )
}
function artistPlaying(a) {
  return artistRows(a).some(isPlayingRow)
}
function playArtist(a) {
  const rows = artistRows(a)
  if (!rows.length) return openArtistOf(a)
  if (artistPlaying(a)) return player.toggle()
  playRows(rows, 0, { toggle: false })
}
// Their page: on YouTube Music when the app knows them there, in the library
// when songs of theirs are saved, else a search for them.
function openArtistOf(a) {
  if (!a) return
  if (a.id) openArtist({ id: a.id, name: a.name })
  else if (artistRows(a).some((r) => r.kind === 'local')) router.push({ name: 'Artist', params: { name: a.name } })
  else router.push({ name: 'Search', params: { query: a.name } })
}
function openAlbum(a) {
  if (a.album_id) router.push({ name: 'ExploreAlbum', params: { id: a.album_id } })
  else router.push({ name: 'Search', params: { query: `${a.artist || ''} ${a.name}`.trim() } })
}

// A moment about a song plays it; one about an artist plays them.
function momentGo(m) {
  if (m.song) return () => playOne(entryRow(m.song))
  if (m.artist) return () => playArtist({ name: m.artist, id: m.id || '' })
  return null
}
function momentPlaying(m) {
  if (m.song) return isPlayingRow(entryRow(m.song))
  return m.artist ? artistPlaying({ name: m.artist }) : false
}

// The music following the story: the year's first song on its page, the top
// artist's song on theirs, the song of the year on its own.
const FOLLOW_KEY = 'dn.recapFollow'
function storedFollow() {
  try {
    return localStorage.getItem(FOLLOW_KEY) === '1'
  } catch {
    return false
  }
}
const follow = ref(storedFollow())
const slideTrack = computed(() => {
  switch (slide.value.id) {
    case 'first':
      return firstRow.value
    case 'artist':
      return artistRows(topArtist.value)[0] || null
    case 'song':
      return songRows.value[0] || null
    case 'habits':
      return repeatRow.value
    case 'moments': {
      const m = moments.value.find((x) => x.song)
      return m ? entryRow(m.song) : null
    }
    default:
      return null
  }
})
function followSlide(starting = false) {
  if (!follow.value || state.value !== 'ready') return
  const row = slideTrack.value
  if (row) {
    if (!isRowCurrent(row)) playOne(row, { toggle: false })
  } else if (starting && !player.isPlaying.value) {
    playTop()
  }
}
function setFollow(on) {
  follow.value = on
  try {
    localStorage.setItem(FOLLOW_KEY, on ? '1' : '0')
  } catch {
    // kept for this visit only
  }
  followSlide(on)
}
watch(() => slide.value.id, () => followSlide())
function startWithMusic() {
  follow.value = true
  try {
    localStorage.setItem(FOLLOW_KEY, '1')
  } catch {
    // kept for this visit only
  }
  go(1)
  followSlide(true)
}
// The summary as a picture (model/shareCard.js, fetched when first asked).
const sharing = ref('')
async function shareCard(how) {
  if (sharing.value || !data.value) return
  sharing.value = how
  try {
    const { drawCard, copyCard, toBase64 } = await import('/src/model/shareCard')
    const blob = await drawCard({
      title: summaryTitle.value,
      eyebrow: t('recap.eyebrow'),
      hue: PERIOD_HUE[period.value],
      minutes: number(minutes.value),
      minutesUnit: t('recap.minutesUnit'),
      artist: topArtist.value ? { name: topArtist.value.name, picture: artistPicture(topArtist.value, 600) } : null,
      songs: songRows.value.slice(0, 5).map((r) => r.title),
      artists: (data.value.top_artists || []).map((a) => a.name),
      words: {
        topArtist: t('recap.topArtist'),
        topSongs: t('recap.topSongs'),
        topArtists: t('recap.topArtists'),
        footer: t('recap.cardFooter'),
      },
    })
    if (how === 'copy') {
      await copyCard(blob)
      toast(t('recap.shareCopied'), { icon: 'ph:check-circle-fill', tone: 'success' })
    } else {
      await API.saveShareImage(summaryTitle.value, await toBase64(blob))
      toast(t('recap.shareSaved'), { icon: 'ph:check-circle-fill', tone: 'success' })
    }
  } catch {
    toast(t('recap.shareFailed'), { tone: 'error' })
  } finally {
    sharing.value = ''
  }
}

const playlists = usePlaylists()
function saveTop() {
  if (!songRows.value.length) return
  const name =
    period.value === 'year'
      ? t('recap.playlistName', { year: year.value })
      : t(`story.playlist.${period.value}`, { date: isoText(data.value.start), month: title.value })
  playlists.createPlaylist(songRows.value, { name })
}

// --- Words ---------------------------------------------------------------------------
const formatter = computed(() => new Intl.NumberFormat(locale.value || 'en'))
function number(n) {
  return formatter.value.format(n || 0)
}
function isoText(iso) {
  const [y, m, d] = String(iso).split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(locale.value || 'en', { day: 'numeric', month: 'long' })
}
function dateText(seconds) {
  return new Date(seconds * 1000).toLocaleDateString(locale.value || 'en', { day: 'numeric', month: 'long' })
}
function monthText(m, month = 'long') {
  return new Date(year.value, m, 1).toLocaleDateString(locale.value || 'en', { month })
}
function timeText(seconds) {
  return new Date(seconds * 1000).toLocaleTimeString(locale.value || 'en', { hour: 'numeric', minute: '2-digit' })
}
// The name of each part of the stretch.
const DAY_PARTS = ['night', 'morning', 'afternoon', 'evening']
function partText(i) {
  if (period.value === 'year') return monthText(i, 'short')
  if (period.value === 'month') return t('story.weekN', { n: i + 1 })
  if (period.value === 'week') return weekdayText((i + firstDay.value) % 7)
  return t(`story.part.${DAY_PARTS[i]}`)
}
function weekdayText(d, weekday = 'short') {
  // 5 January 2026 was a Monday: Monday first, as the week is counted.
  return new Date(2026, 0, 5 + d).toLocaleDateString(locale.value || 'en', { weekday })
}
function hourShort(h) {
  return new Intl.DateTimeFormat(locale.value || 'en', { hour: 'numeric' }).format(new Date(2026, 0, 1, h))
}
</script>

<style scoped>
.recap {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 100%;
  overflow: hidden;
  color: #fff;
  outline: none;
  /* The colour under the moving layer, so nothing dark shows at its edges. */
  background: #6b1d6e;
  --c-fg: 255 255 255;
  --c-tint: 255 255 255;
}
/* The slowly moving colours, on a layer of their own: moved, never redrawn.
   Each slide turns their hue. */
.recap-bg {
  position: absolute;
  inset: -40%;
  background: linear-gradient(130deg, #2b0d4a, #6b1d6e 40%, #c2185b 75%, #ff6f3c);
  filter: hue-rotate(var(--hue));
  transition: filter 1.1s ease;
  pointer-events: none;
}
.recap-glow {
  position: absolute;
  inset: -20%;
  background:
    radial-gradient(40% 35% at 20% 25%, rgb(255 255 255 / 0.16), transparent 70%),
    radial-gradient(45% 40% at 80% 75%, rgb(255 190 120 / 0.18), transparent 70%);
  animation: recap-float 14s ease-in-out infinite alternate;
  pointer-events: none;
}
.recap-mosaic {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 18px;
  padding: 6%;
  opacity: 0.08;
  transform: rotate(-8deg) scale(1.25);
  pointer-events: none;
  filter: grayscale(1);
}
.recap-tile {
  aspect-ratio: 1;
  border-radius: 14px;
  background-size: cover;
  background-position: center;
  animation: recap-drift 16s ease-in-out infinite alternate;
  animation-delay: calc(var(--i) * -2s);
}
@keyframes recap-float {
  from {
    transform: translate(0, 0) scale(1);
  }
  to {
    transform: translate(3%, -2%) scale(1.06);
  }
}
@keyframes recap-drift {
  to {
    transform: translateY(-14px);
  }
}
.recap-top {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px 0;
}
.recap-steps {
  display: flex;
  flex: 1;
  gap: 5px;
}
.recap-step {
  display: grid;
  flex: 1;
  align-items: center;
  height: 18px;
  cursor: pointer;
}
.recap-step-track {
  height: 3px;
  overflow: hidden;
  border-radius: 999px;
  background: rgb(255 255 255 / 0.28);
  transition: height 0.15s ease;
}
.recap-step:hover .recap-step-track,
.recap-step:focus-visible .recap-step-track {
  height: 6px;
}
.recap-step:focus-visible {
  outline: none;
}
.recap-step i {
  display: block;
  height: 100%;
  background: #fff;
  transform-origin: left;
}
.recap-year {
  height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgb(255 255 255 / 0.3);
  background: rgb(0 0 0 / 0.2);
  color: #fff;
  font-weight: 600;
}
.recap-btn {
  color: rgb(255 255 255 / 0.85);
}
/* Today, this week, this month, the year: glass pills under the bars. */
.recap-periods {
  position: relative;
  z-index: 1;
  display: flex;
  align-self: center;
  gap: 2px;
  margin-top: 12px;
  padding: 3px;
  border-radius: 999px;
  background: rgb(0 0 0 / 0.22);
  box-shadow: inset 0 0 0 1px rgb(255 255 255 / 0.14);
  backdrop-filter: blur(10px);
}
.recap-period {
  height: 30px;
  padding: 0 14px;
  border-radius: 999px;
  font-size: 0.82rem;
  font-weight: 700;
  color: rgb(255 255 255 / 0.78);
  transition:
    background-color 0.2s ease,
    color 0.2s ease;
}
.recap-period:hover {
  color: #fff;
  background: rgb(255 255 255 / 0.12);
}
.recap-period.is-back {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-left: 4px;
  box-shadow: inset 1px 0 0 rgb(255 255 255 / 0.18);
  border-radius: 0 999px 999px 0;
}
.recap-period.is-back[aria-pressed='true'] {
  color: #2b0d4a;
  background: #fff;
  border-radius: 999px;
}
.recap-period.is-on {
  color: #2b0d4a;
  background: #fff;
  box-shadow: 0 6px 18px rgb(0 0 0 / 0.25);
}
.recap-period:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 2px;
}
/* Hello, by name. */
.recap-hey {
  font-size: clamp(1.3rem, 3.4vw, 2rem);
  font-weight: 800;
  letter-spacing: -0.02em;
  --an-ink: #fff;
  --an-shine: #ffe08a;
}
.recap-btn:hover:not(:disabled) {
  color: #fff;
  background: rgb(255 255 255 / 0.14);
}
.recap-btn.is-on,
.recap-btn.is-on:hover {
  color: #111;
  background: #fff;
}
/* What plays: a round white button that comes up over it. */
.recap-play {
  position: relative;
  display: block;
  padding: 0;
  cursor: pointer;
}
.recap-play-mark {
  position: absolute;
  right: 12px;
  bottom: 12px;
  display: grid;
  width: 56px;
  height: 56px;
  place-items: center;
  border-radius: 999px;
  background: #fff;
  color: #111;
  box-shadow: 0 10px 26px rgb(0 0 0 / 0.35);
  opacity: 0;
  transform: scale(0.8) translateY(6px);
  transition:
    opacity 0.18s ease,
    transform 0.22s cubic-bezier(0.2, 0.9, 0.2, 1.2);
  pointer-events: none;
}
.recap-play-mark.is-small {
  right: 4px;
  bottom: 4px;
  width: 34px;
  height: 34px;
}
.recap-play:hover .recap-play-mark,
.recap-play:focus-visible .recap-play-mark,
.recap-play.is-current .recap-play-mark,
.recap-artist:hover .recap-play-mark,
.recap-artist:focus-visible .recap-play-mark,
.recap-artist.is-current .recap-play-mark,
.recap-album:hover .recap-play-mark,
.recap-album:focus-visible .recap-play-mark {
  opacity: 1;
  transform: none;
}
.recap-play:focus-visible,
.recap-artist:focus-visible,
.recap-album:focus-visible,
.recap-row:focus-visible,
.recap-month-tile:focus-visible,
.recap-fact.is-playable:focus-visible,
.recap-card-item:focus-visible,
.recap-mini:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 3px;
}
.recap-play.is-current {
  box-shadow:
    0 0 0 4px rgb(255 255 255 / 0.85),
    0 24px 60px rgb(0 0 0 / 0.4);
}
.recap-mini {
  position: absolute;
  top: 0;
  right: 8px;
  z-index: 1;
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 999px;
  background: rgb(0 0 0 / 0.35);
  color: #fff;
  opacity: 0;
  transition:
    opacity 0.15s ease,
    background-color 0.15s ease;
}
.recap-artist-item:hover .recap-mini,
.recap-mini:focus-visible {
  opacity: 1;
}
.recap-mini:hover {
  background: rgb(0 0 0 / 0.6);
}
/* Three bars that move, where the number was, while the song plays. */
.recap-eq {
  display: inline-flex;
  align-items: flex-end;
  gap: 2px;
  height: 16px;
}
.recap-eq i {
  width: 3px;
  height: 100%;
  border-radius: 2px;
  background: #fff;
  transform-origin: bottom;
  animation: recap-eq 0.9s ease-in-out infinite;
}
.recap-eq i:nth-child(2) {
  animation-delay: -0.3s;
}
.recap-eq i:nth-child(3) {
  animation-delay: -0.6s;
}
@keyframes recap-eq {
  0%,
  100% {
    transform: scaleY(0.3);
  }
  50% {
    transform: scaleY(1);
  }
}
.recap-center,
.recap-slide {
  position: relative;
  z-index: 1;
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px clamp(20px, 6vw, 72px);
  text-align: center;
}
.recap-center {
  min-height: 0;
}
/* A page taller than the window scrolls within itself, the bars, the tabs
   and the arrows staying where they are; "safe" keeps its top reachable. */
.recap-slide {
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  justify-content: safe center;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: rgb(255 255 255 / 0.35) transparent;
  cursor: pointer;
  user-select: none;
}
/* Whole, never squeezed: a card that does not fit is scrolled to, not cut. */
.recap-slide > * {
  flex-shrink: 0;
}
.recap-eyebrow {
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgb(255 255 255 / 0.78);
  animation: recap-in 0.5s ease both;
}
.recap-huge {
  font-size: clamp(4rem, 14vw, 9rem);
  font-weight: 900;
  line-height: 0.95;
  letter-spacing: -0.05em;
  font-variant-numeric: tabular-nums;
  animation: recap-pop 0.6s cubic-bezier(0.2, 0.9, 0.2, 1.2) both;
}
.recap-huge.is-words {
  font-size: clamp(3rem, 10vw, 6.5rem);
  letter-spacing: -0.04em;
}
.recap-big {
  font-size: clamp(2rem, 6vw, 3.6rem);
  font-weight: 800;
  line-height: 1.05;
  letter-spacing: -0.03em;
  max-width: 18ch;
  overflow-wrap: anywhere;
  animation: recap-in 0.55s ease 0.1s both;
}
.recap-lead {
  font-size: clamp(1.05rem, 2.4vw, 1.5rem);
  font-weight: 600;
  color: rgb(255 255 255 / 0.92);
  animation: recap-in 0.55s ease 0.2s both;
}
.recap-small {
  max-width: 44ch;
  font-size: 1rem;
  color: rgb(255 255 255 / 0.8);
  animation: recap-in 0.55s ease 0.3s both;
}
.recap-ctas {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  margin-top: 10px;
}
.recap-cta {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 46px;
  padding: 0 24px;
  border-radius: 999px;
  background: #fff;
  color: #3a0f4f;
  font-weight: 700;
  box-shadow: 0 12px 30px rgb(0 0 0 / 0.25);
  transition: transform 0.15s ease;
}
.recap-cta.is-ghost {
  background: rgb(255 255 255 / 0.14);
  color: #fff;
  box-shadow: inset 0 0 0 1px rgb(255 255 255 / 0.35);
}
.recap-cta:hover:not(:disabled) {
  transform: scale(1.04);
}
.recap-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 999px;
  background: rgb(0 0 0 / 0.22);
  font-size: 0.92rem;
  font-weight: 600;
  animation: recap-in 0.55s ease 0.35s both;
}
.recap-pill.is-up {
  background: rgb(30 215 96 / 0.25);
}
.recap-pill.is-down {
  background: rgb(0 0 0 / 0.3);
}
.recap-chips {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}
.recap-portrait .recap-play-mark {
  right: 6%;
  bottom: 6%;
}
.recap-portrait {
  width: clamp(140px, 24vw, 220px);
  aspect-ratio: 1;
  border-radius: 999px;
  box-shadow: 0 20px 50px rgb(0 0 0 / 0.35);
  animation: recap-pop 0.6s cubic-bezier(0.2, 0.9, 0.2, 1.2) both;
}
.recap-cover {
  width: clamp(150px, 26vw, 240px);
  aspect-ratio: 1;
  border-radius: 16px;
  box-shadow: 0 24px 60px rgb(0 0 0 / 0.4);
  animation: recap-pop 0.6s cubic-bezier(0.2, 0.9, 0.2, 1.2) both;
}
.recap-cover.is-tilted {
  transform: rotate(-4deg);
}
.recap-artists {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 150px));
  justify-content: center;
  gap: 18px;
  width: min(900px, 100%);
}
.recap-artist-item {
  position: relative;
  min-width: 0;
  animation: recap-in 0.45s ease both;
  animation-delay: calc(var(--i) * 90ms);
}
.recap-artist {
  position: relative;
  display: grid;
  justify-items: center;
  gap: 6px;
  width: 100%;
  min-width: 0;
  padding: 4px 4px 8px;
  border-radius: 16px;
  cursor: pointer;
  transition: background-color 0.15s ease;
}
.recap-artist:hover,
.recap-artist.is-current {
  background: rgb(255 255 255 / 0.1);
}
.recap-artist-pic-wrap {
  position: relative;
  display: block;
}
.recap-artist .recap-rank {
  position: absolute;
  top: -4px;
  left: 6px;
  z-index: 1;
}
.recap-artist-pic {
  width: 110px;
  height: 110px;
  box-shadow: 0 12px 30px rgb(0 0 0 / 0.3);
}
.recap-artist .recap-row-title,
.recap-artist .recap-row-sub {
  max-width: 100%;
}
.recap-list {
  display: grid;
  gap: 8px;
  width: min(560px, 100%);
  text-align: left;
}
.recap-row-item {
  animation: recap-in 0.45s ease both;
  animation-delay: calc(var(--i) * 80ms);
}
.recap-row {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  padding: 8px 12px;
  border-radius: 12px;
  text-align: left;
  background: rgb(0 0 0 / 0.18);
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    transform 0.15s ease;
}
.recap-row:hover {
  background: rgb(0 0 0 / 0.3);
  transform: translateX(4px);
}
.recap-row.is-current {
  background: rgb(255 255 255 / 0.18);
}
.recap-thumb-wrap {
  position: relative;
  flex: none;
}
.recap-thumb-play {
  position: absolute;
  inset: 0;
  margin: auto;
  color: #fff;
  filter: drop-shadow(0 2px 6px rgb(0 0 0 / 0.6));
  opacity: 0;
  transition: opacity 0.15s ease;
}
.recap-row:hover .recap-thumb-play {
  opacity: 1;
}
.recap-rank {
  width: 1.5em;
  font-size: 1.3rem;
  font-weight: 800;
  text-align: center;
}
.recap-thumb {
  width: 48px;
  height: 48px;
  flex: none;
}
.recap-row-title,
.recap-row-sub {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recap-row-title {
  font-weight: 700;
}
.recap-row-sub {
  font-size: 0.85rem;
  color: rgb(255 255 255 / 0.75);
}
.recap-row-count {
  flex: none;
  font-size: 0.8rem;
  color: rgb(255 255 255 / 0.75);
}
.recap-albums {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 160px));
  justify-content: center;
  gap: 18px;
  width: min(900px, 100%);
}
.recap-album {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 0;
  text-align: left;
  cursor: pointer;
  animation: recap-in 0.45s ease both;
  animation-delay: calc(var(--i) * 80ms);
}
.recap-album-art-wrap {
  position: relative;
  display: block;
  transition: transform 0.2s ease;
}
.recap-album:hover .recap-album-art-wrap {
  transform: translateY(-4px);
}
.recap-album-words {
  display: grid;
  min-width: 0;
}
.recap-album-art {
  width: 100%;
  aspect-ratio: 1;
  box-shadow: 0 12px 30px rgb(0 0 0 / 0.3);
}
/* Month by month */
.recap-months-grid {
  display: grid;
  grid-template-columns: repeat(var(--cols, 6), minmax(0, 1fr));
  gap: 12px;
  width: min(820px, 100%);
}
.recap-month-tile {
  display: grid;
  justify-items: center;
  gap: 4px;
  min-width: 0;
  padding: 10px 6px;
  border-radius: 14px;
  background: rgb(0 0 0 / 0.18);
  animation: recap-in 0.45s ease both;
  animation-delay: calc(var(--i) * 55ms);
}
.recap-month-tile.is-empty {
  opacity: 0.45;
}
button.recap-month-tile {
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    transform 0.15s ease;
}
button.recap-month-tile:hover,
.recap-month-tile.is-current {
  background: rgb(255 255 255 / 0.16);
  transform: translateY(-3px);
}
.recap-month-art {
  width: 100%;
  max-width: 84px;
  aspect-ratio: 1;
}
.recap-month-art.is-blank {
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: rgb(255 255 255 / 0.08);
  color: rgb(255 255 255 / 0.4);
}
.recap-month-name {
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: rgb(255 255 255 / 0.75);
}
.recap-month-who {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.82rem;
  font-weight: 700;
}
/* The day's clock and the week */
.recap-clock-wrap {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 28px;
}
.recap-clock {
  width: clamp(240px, 34vw, 340px);
  height: auto;
  overflow: visible;
}
.recap-clock-face {
  fill: rgb(0 0 0 / 0.2);
}
.recap-clock-bar {
  fill: rgb(255 255 255 / 0.55);
  transform-box: fill-box;
  transform-origin: bottom;
  animation: recap-grow 0.6s ease both;
  animation-delay: calc(var(--i) * 25ms);
}
.recap-clock-bar.is-peak {
  fill: #fff;
}
.recap-clock-label {
  fill: rgb(255 255 255 / 0.8);
  font-size: 9px;
  font-weight: 700;
  text-anchor: middle;
  dominant-baseline: middle;
}
.recap-week {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  height: 170px;
}
.recap-week-col {
  display: flex;
  height: 100%;
  flex-direction: column;
  justify-content: flex-end;
  align-items: center;
  gap: 6px;
}
.recap-week-bar {
  width: 26px;
  height: var(--h);
  border-radius: 6px 6px 3px 3px;
  background: rgb(255 255 255 / 0.5);
  transform-origin: bottom;
  animation: recap-grow 0.6s ease both;
  animation-delay: calc(var(--i) * 50ms);
}
.recap-week-col.is-peak .recap-week-bar {
  background: #fff;
}
.recap-week-day {
  font-size: 0.72rem;
  font-weight: 700;
  color: rgb(255 255 255 / 0.8);
}
.recap-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 14px;
  width: min(820px, 100%);
}
.recap-fact {
  display: grid;
  justify-items: center;
  align-content: start;
  gap: 6px;
  padding: 22px 16px;
  border-radius: 18px;
  background: rgb(0 0 0 / 0.2);
  animation: recap-in 0.45s ease both;
  animation-delay: calc(var(--i) * 90ms);
}
.recap-fact.is-playable {
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    transform 0.15s ease;
}
.recap-fact.is-playable:hover,
.recap-fact.is-current {
  background: rgb(255 255 255 / 0.16);
  transform: translateY(-3px);
}
.recap-fact-icon {
  width: 28px;
  height: 28px;
  color: rgb(255 255 255 / 0.85);
}
.recap-fact-value {
  font-size: 1.6rem;
  font-weight: 800;
}
.recap-fact-song {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 1.15rem;
}
.recap-fact-label {
  font-size: 0.9rem;
  color: rgb(255 255 255 / 0.8);
}
.recap-months {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  width: min(420px, 100%);
  height: 90px;
  margin-top: 10px;
}
.recap-month {
  flex: 1;
  height: var(--h);
  border-radius: 4px 4px 2px 2px;
  background: rgb(255 255 255 / 0.85);
  transform-origin: bottom;
  animation: recap-grow 0.6s ease both;
  animation-delay: calc(var(--i) * 40ms);
}
/* The card as a picture: round buttons beside the others. */
.recap-cta.is-icon {
  width: 46px;
  padding: 0;
  justify-content: center;
}
.recap-cta:disabled {
  cursor: progress;
}
/* The moments */
.recap-moments {
  display: grid;
  gap: 10px;
  width: min(620px, 100%);
}
.recap-moment-item {
  animation: recap-in 0.5s cubic-bezier(0.2, 0.9, 0.2, 1.1) both;
  animation-delay: calc(var(--i) * 140ms + 120ms);
}
.recap-moment {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  padding: 14px 18px 14px 14px;
  border-radius: 18px;
  background: rgb(0 0 0 / 0.2);
  box-shadow: inset 0 0 0 1px rgb(255 255 255 / 0.1);
  text-align: left;
  transition:
    background-color 0.15s ease,
    transform 0.15s ease;
}
.recap-moment.is-top {
  background: linear-gradient(120deg, rgb(255 255 255 / 0.26), rgb(255 255 255 / 0.1));
  box-shadow:
    inset 0 0 0 1px rgb(255 255 255 / 0.35),
    0 18px 40px rgb(0 0 0 / 0.25);
}
.recap-moment.is-playable {
  cursor: pointer;
}
.recap-moment.is-playable:hover,
.recap-moment.is-current {
  background: rgb(255 255 255 / 0.2);
  transform: translateY(-2px);
}
.recap-moment:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 3px;
}
.recap-moment-icon {
  display: grid;
  flex: none;
  width: 42px;
  height: 42px;
  place-items: center;
  border-radius: 14px;
  background: rgb(255 255 255 / 0.18);
}
.recap-moment.is-top .recap-moment-icon {
  background: #fff;
  color: #2b0d4a;
  animation: recap-beat 1.6s ease-in-out 0.8s 2;
}
.recap-moment-text {
  flex: 1;
  min-width: 0;
  font-size: clamp(0.98rem, 2vw, 1.15rem);
  font-weight: 700;
  line-height: 1.3;
}
.recap-moment-go {
  flex: none;
  opacity: 0.7;
}
@keyframes recap-beat {
  0%,
  100% {
    transform: scale(1);
  }
  30% {
    transform: scale(1.14) rotate(-6deg);
  }
  60% {
    transform: scale(0.96);
  }
}
/* Personality */
.recap-persona-mark {
  display: grid;
  width: 120px;
  height: 120px;
  place-items: center;
  border-radius: 36px;
  background: rgb(255 255 255 / 0.16);
  box-shadow:
    inset 0 0 0 1px rgb(255 255 255 / 0.3),
    0 24px 60px rgb(0 0 0 / 0.3);
  animation: recap-pop 0.7s cubic-bezier(0.2, 0.9, 0.2, 1.2) both;
}
.recap-persona-text {
  max-width: 36ch;
}
/* The card */
.recap-card {
  width: min(560px, 100%);
  overflow: hidden;
  border-radius: 24px;
  background: linear-gradient(160deg, rgb(255 255 255 / 0.22), rgb(255 255 255 / 0.06));
  box-shadow:
    inset 0 0 0 1px rgb(255 255 255 / 0.25),
    0 30px 80px rgb(0 0 0 / 0.35);
  text-align: left;
  cursor: default;
  animation: recap-pop 0.6s cubic-bezier(0.2, 0.9, 0.2, 1.2) both;
}
.recap-card-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 22px;
  border-bottom: 1px solid rgb(255 255 255 / 0.15);
  font-weight: 800;
}
.recap-card-brand {
  letter-spacing: -0.02em;
}
.recap-card-year {
  color: rgb(255 255 255 / 0.85);
}
.recap-card-body {
  display: grid;
  gap: 18px;
  padding: 20px 22px 22px;
}
.recap-card-artist {
  display: grid;
  justify-items: center;
  gap: 4px;
  text-align: center;
}
.recap-card-pic {
  width: 110px;
  height: 110px;
  margin-bottom: 6px;
}
.recap-card-cols,
.recap-card-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.recap-card-label {
  margin-bottom: 4px;
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgb(255 255 255 / 0.7);
}
.recap-card-name {
  font-size: 1.4rem;
  font-weight: 800;
}
.recap-card-list {
  display: grid;
  gap: 4px;
  font-size: 0.92rem;
  font-weight: 600;
}
.recap-card-list li {
  min-width: 0;
}
.recap-card-item {
  display: block;
  width: calc(100% + 8px);
  margin-left: -4px;
  padding: 1px 4px;
  overflow: hidden;
  border-radius: 6px;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 0.15s ease;
}
.recap-card-item:hover,
.recap-card-item.is-current {
  background: rgb(255 255 255 / 0.14);
}
.recap-card-list b {
  display: inline-block;
  width: 1.4em;
  font-weight: 800;
  color: rgb(255 255 255 / 0.65);
}
.recap-card-num {
  font-size: 1.8rem;
  font-weight: 900;
  font-variant-numeric: tabular-nums;
}
.recap-card-num.is-text {
  font-size: 1.15rem;
  line-height: 1.3;
}
.recap-nav {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: center;
  gap: 12px;
  padding: 0 0 22px;
}
@keyframes recap-pop {
  from {
    opacity: 0;
    transform: scale(0.85);
  }
}
@keyframes recap-in {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
}
@keyframes recap-grow {
  from {
    transform: scaleY(0);
  }
}
.slide-next-enter-active,
.slide-next-leave-active,
.slide-prev-enter-active,
.slide-prev-leave-active {
  transition:
    opacity 0.28s ease,
    transform 0.28s ease;
}
.slide-next-enter-from,
.slide-prev-leave-to {
  opacity: 0;
  transform: translateX(28px);
}
.slide-next-leave-to,
.slide-prev-enter-from {
  opacity: 0;
  transform: translateX(-28px);
}
/* A short window (a 768-pixel laptop screen, or a window made small): every
   page a size smaller, so most fit without scrolling. */
@media (max-height: 820px) {
  .recap-top {
    padding-top: 10px;
  }
  .recap-periods {
    margin-top: 8px;
  }
  .recap-period {
    height: 26px;
    padding: 0 12px;
    font-size: 0.78rem;
  }
  .recap-center,
  .recap-slide {
    gap: 8px;
    padding-top: 14px;
    padding-bottom: 14px;
  }
  .recap-hey {
    font-size: clamp(1.1rem, 4vh, 2rem);
  }
  .recap-huge {
    font-size: clamp(2.8rem, 15vh, 9rem);
  }
  .recap-huge.is-words {
    font-size: clamp(2.2rem, 11vh, 6.5rem);
  }
  .recap-big {
    font-size: clamp(1.5rem, 6.5vh, 3.6rem);
  }
  .recap-lead {
    font-size: clamp(0.95rem, 2.8vh, 1.5rem);
  }
  .recap-cover {
    width: clamp(110px, 28vh, 240px);
  }
  .recap-portrait {
    width: clamp(100px, 25vh, 220px);
  }
  .recap-clock {
    width: clamp(170px, 36vh, 340px);
  }
  .recap-persona-mark {
    width: 84px;
    height: 84px;
    border-radius: 26px;
  }
  .recap-moments {
    gap: 7px;
  }
  .recap-moment {
    padding: 9px 14px 9px 10px;
    border-radius: 14px;
  }
  .recap-moment-icon {
    width: 34px;
    height: 34px;
    border-radius: 11px;
  }
  .recap-moment-text {
    font-size: 0.95rem;
  }
  .recap-fact {
    padding: 14px 12px;
  }
  .recap-fact-value {
    font-size: 1.3rem;
  }
  .recap-nav {
    padding-bottom: 10px;
  }
  .recap-nav .recap-btn {
    width: 32px;
    height: 32px;
  }
}
@media (max-height: 620px) {
  .recap-ctas {
    margin-top: 4px;
  }
  .recap-cta {
    height: 38px;
    padding: 0 18px;
  }
  .recap-card-body {
    gap: 12px;
    padding: 14px 18px 16px;
  }
  .recap-card-pic {
    width: 72px;
    height: 72px;
  }
}
@media (max-width: 700px) {
  .recap-months-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
@media (prefers-reduced-motion: reduce) {
  .recap-bg,
  .recap-glow,
  .recap-tile,
  .recap-huge,
  .recap-big,
  .recap-lead,
  .recap-small,
  .recap-eyebrow,
  .recap-pill,
  .recap-portrait,
  .recap-cover,
  .recap-row,
  .recap-album,
  .recap-artist,
  .recap-month-tile,
  .recap-clock-bar,
  .recap-week-bar,
  .recap-fact,
  .recap-month,
  .recap-persona-mark,
  .recap-moment-item,
  .recap-moment-icon,
  .recap-card {
    animation: none !important;
  }
  .recap-bg {
    transition: none;
  }
}
</style>
