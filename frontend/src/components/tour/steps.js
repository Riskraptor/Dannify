// The tours, as data. Each step points at something named with data-tour
// (`target`), says where its words go (`place`), which page it is on
// (`route`), and whether it waits for the person to try it (`try`: 'type' in
// the box, or 'click' on `tryTarget`). A step whose target is not on screen
// is passed over when it is `optional`, and said in the middle otherwise.
// Its words are tour.<id>Title, tour.<id>Text and, for a try, tour.<id>Try.

export const TOURS = {
  welcome: [
    { id: 'hello', icon: 'ph:hand-waving-fill' },
    { id: 'search', target: 'search', place: 'bottom', try: 'type' },
    { id: 'lately', target: 'lately', place: 'bottom', route: 'Home', optional: true },
    { id: 'library', target: 'library', place: 'right' },
    { id: 'player', target: 'player', place: 'top', try: 'click', tryTarget: 'np-cover' },
    { id: 'lyrics', target: 'lyrics-btn', place: 'top' },
    { id: 'sound', target: 'sound', place: 'top' },
    { id: 'stats', target: 'nav-stats', place: 'right' },
    { id: 'settings', target: 'nav-settings', place: 'right' },
    { id: 'done', icon: 'ph:confetti-fill', celebrate: true },
  ],
  new: [
    { id: 'newHello', icon: 'ph:sparkle-fill' },
    { id: 'newLinks', target: 'search', place: 'bottom' },
    { id: 'newCharts', target: 'charts', place: 'top', route: 'Search', optional: true },
    { id: 'newStats', target: 'highlights', place: 'bottom', route: 'Stats', optional: true },
    { id: 'newPlayer', target: 'player', place: 'top' },
    { id: 'newDone', icon: 'ph:confetti-fill', celebrate: true },
  ],
}
