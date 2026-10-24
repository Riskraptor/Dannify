// Going to a page from a model that the pages themselves load. Importing the
// router there would load every page with it, inside the player's own
// imports; the router is handed over here once the app starts (main.js).

let router = null

export function setNavigator(r) {
  router = r
}

/** Go to *to* (a route location), once the app has started. */
export function navigate(to) {
  return router ? router.push(to) : Promise.resolve()
}
