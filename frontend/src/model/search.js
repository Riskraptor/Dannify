import { ref } from 'vue'

import API from '/src/model/api'

// The query the title-bar search box and the Search view share. Dannify is
// search-first: there is no "paste a link" mode any more, so this is just
// the live term plus the legacy /api/songs/search helper a few callers use.

const searchTerm = ref('')
const results = ref()
const isSearching = ref(false)
const error = ref(false)
const errorValue = ref('')

function useSearchManager() {
  function searchFor(query) {
    results.value = []
    isSearching.value = true
    searchTerm.value = query
    error.value = false
    errorValue.value = ''
    API.search(query)
      .then((res) => {
        if (res.status === 200) {
          results.value = res.data
        } else {
          error.value = true
          errorValue.value = res.toString()
        }
      })
      .catch((err) => {
        error.value = true
        errorValue.value = err.message
      })
      .finally(() => {
        isSearching.value = false
      })
  }

  return {
    searchTerm,
    isSearching,
    results,
    error,
    errorValue,
    searchFor,
  }
}

export { useSearchManager }
