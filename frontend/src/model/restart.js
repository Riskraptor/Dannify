import { desktop } from '/src/desktop/bridge'
import { confirmDialog } from '/src/model/dialog'
import { toast } from '/src/model/toast'
import { t } from '/src/i18n'

// Some preferences only take effect on a fresh window (the native title bar
// is one). Instead of leaving a dead "restart to apply" note behind, ask
// and actually do it. Declining is remembered as a toast the user can act on
// later, so nothing gets stuck in a half-applied state silently.

let pending = false

/**
 * Offer to restart now. Returns true when the app is on its way down.
 * @param {string} message why a restart is needed
 */
export async function promptRestart(message) {
  if (!desktop.isDesktop) {
    toast(t('restart.reloadInstead'), { icon: 'ph:arrow-clockwise' })
    return false
  }
  if (pending) return false
  pending = true
  try {
    const now = await confirmDialog({
      title: t('restart.title'),
      message,
      detail: t('restart.detail'),
      confirmText: t('restart.now'),
      cancelText: t('restart.later'),
      icon: 'ph:arrow-clockwise',
    })
    if (!now) {
      toast(t('restart.deferred'), {
        icon: 'ph:clock',
        timeout: 6000,
        action: { label: t('restart.now'), run: () => desktop.restart() },
      })
      return false
    }
    const ok = await desktop.restart()
    if (!ok) toast(t('restart.failed'), { tone: 'error' })
    return !!ok
  } finally {
    pending = false
  }
}
