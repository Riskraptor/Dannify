// Slim scrollbars that float over the content, the way Windows 11's own apps
// draw them: out of sight until the pane is scrolled or the pointer comes near
// its edge, thin until hovered, and never taking width from the page.
//
// The browser's bar took a 12 pixel strip down the right of every pane that
// scrolled, so the page also moved sideways by that much going between one
// that scrolls and one that does not, and it looked like a web page.
//
//   <main v-overlay-scroll>          the element that scrolls
//   <div v-overlay-scroll="false">   leave this one alone
//
// The bar is a zero-height sticky element put in as the scroller's first
// child: it stays at the top of the visible area whatever the scroll, is
// clipped with the pane, and sits above the pane's own sticky headers.

const IDLE_MS = 1100
const MIN_THUMB = 36
const PAD = 3 // from the pane's top and bottom edges
const NEAR = 28 // px from the right edge where the pointer brings the bar up

function attach(el) {
  // In a flex or grid container the bar would be laid out as one of the
  // items and push the content along. Those keep the plain thin scrollbar.
  if (/flex|grid/.test(getComputedStyle(el).display)) return null
  el.classList.add('os-host')
  // Also inline: a component that binds its own classes rewrites the class
  // list whenever they change, and the class alone would go with it.
  el.style.scrollbarWidth = 'none'
  const bar = document.createElement('div')
  bar.className = 'os-bar'
  bar.setAttribute('aria-hidden', 'true')
  const track = document.createElement('div')
  track.className = 'os-track'
  const thumb = document.createElement('div')
  thumb.className = 'os-thumb'
  track.appendChild(thumb)
  bar.appendChild(track)
  el.insertBefore(bar, el.firstChild)

  let frame = 0
  let hideTimer = 0
  let drag = null
  let near = false
  let lastHeight = -1
  let scrollable = false

  function geometry() {
    const h = el.clientHeight
    const sh = el.scrollHeight
    const usable = Math.max(0, h - PAD * 2)
    const size = Math.min(usable, Math.max(MIN_THUMB, (usable * h) / Math.max(1, sh)))
    return { h, sh, usable, size }
  }

  function render() {
    frame = 0
    const { h, sh, usable, size } = geometry()
    lastHeight = sh
    scrollable = sh > h + 1 && h > 48 && getComputedStyle(el).overflowY !== 'hidden'
    bar.classList.toggle('is-off', !scrollable)
    if (!scrollable) return
    const room = sh - h
    const pos = room > 0 ? (el.scrollTop / room) * (usable - size) : 0
    track.style.height = `${usable}px`
    thumb.style.height = `${size}px`
    thumb.style.transform = `translateY(${Math.round(pos)}px)`
  }

  function schedule() {
    if (!frame) frame = requestAnimationFrame(render)
  }

  function show() {
    if (!scrollable) return
    bar.classList.add('is-on')
    clearTimeout(hideTimer)
    hideTimer = setTimeout(hide, IDLE_MS)
  }

  function hide() {
    if (drag || near) {
      hideTimer = setTimeout(hide, IDLE_MS)
      return
    }
    bar.classList.remove('is-on')
  }

  const onScroll = () => {
    schedule()
    show()
  }

  const onMove = (e) => {
    const r = el.getBoundingClientRect()
    const isNear = e.clientX >= r.right - NEAR && e.clientX <= r.right
    if (isNear !== near) {
      near = isNear
      bar.classList.toggle('is-near', near)
    }
    if (near) {
      schedule()
      show()
    }
  }

  const onLeave = () => {
    if (near) {
      near = false
      bar.classList.remove('is-near')
    }
  }

  const onDown = (e) => {
    if (e.button !== 0) return
    e.preventDefault()
    e.stopPropagation()
    drag = { y: e.clientY, top: el.scrollTop }
    thumb.setPointerCapture(e.pointerId)
    bar.classList.add('is-drag')
  }

  const onDrag = (e) => {
    if (!drag) return
    const { h, sh, usable, size } = geometry()
    const travel = usable - size
    if (travel <= 0) return
    el.scrollTop = drag.top + ((e.clientY - drag.y) * (sh - h)) / travel
  }

  const onUp = (e) => {
    if (!drag) return
    drag = null
    try {
      thumb.releasePointerCapture(e.pointerId)
    } catch {
      // already released
    }
    bar.classList.remove('is-drag')
    show()
  }

  el.addEventListener('scroll', onScroll, { passive: true })
  el.addEventListener('pointermove', onMove, { passive: true })
  el.addEventListener('pointerleave', onLeave, { passive: true })
  thumb.addEventListener('pointerdown', onDown)
  thumb.addEventListener('pointermove', onDrag)
  thumb.addEventListener('pointerup', onUp)
  thumb.addEventListener('pointercancel', onUp)

  // The pane resizing, and what is in it growing or shrinking (a page
  // changing, a list filling in, pictures arriving).
  const resize = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(schedule) : null
  if (resize) resize.observe(el)
  const poll = setInterval(() => {
    if (document.visibilityState === 'visible' && el.scrollHeight !== lastHeight) schedule()
  }, 600)
  schedule()

  return {
    update() {
      if (el.firstChild !== bar) el.insertBefore(bar, el.firstChild)
      if (!el.classList.contains('os-host')) el.classList.add('os-host')
      schedule()
    },
    destroy() {
      clearInterval(poll)
      clearTimeout(hideTimer)
      if (frame) cancelAnimationFrame(frame)
      if (resize) resize.disconnect()
      el.removeEventListener('scroll', onScroll)
      el.removeEventListener('pointermove', onMove)
      el.removeEventListener('pointerleave', onLeave)
      bar.remove()
      el.classList.remove('os-host')
      el.style.scrollbarWidth = ''
    },
  }
}

export const vOverlayScroll = {
  mounted(el, binding) {
    if (binding.value === false) return
    el.__overlayScroll = attach(el)
    el.__overlayScrollSkipped = !el.__overlayScroll
  },
  updated(el, binding) {
    // Turned on or off since (a list that finds its page's scroller only
    // once the page is up).
    if (binding.value === false) {
      if (el.__overlayScroll) {
        el.__overlayScroll.destroy()
        el.__overlayScroll = null
      }
      return
    }
    if (!el.__overlayScroll) {
      if (!el.__overlayScrollSkipped) {
        el.__overlayScroll = attach(el)
        el.__overlayScrollSkipped = !el.__overlayScroll
      }
      return
    }
    // Vue may have put a node of its own in front of the bar: it goes back
    // to the top, where sticky keeps it.
    el.__overlayScroll.update()
  },
  beforeUnmount(el) {
    if (el.__overlayScroll) {
      el.__overlayScroll.destroy()
      el.__overlayScroll = null
    }
  },
}
