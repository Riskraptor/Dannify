package app.dannify

import android.annotation.SuppressLint
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioManager
import android.net.wifi.WifiManager
import android.os.Build
import android.os.PowerManager
import androidx.core.content.ContextCompat

/**
 * Being a good music app while the music plays: it pauses when the
 * headphones come out, and keeps the phone and the Wi-Fi awake enough to
 * fetch the next song. Only while playing.
 *
 * The audio focus is the page's own. The WebView asks Android for it
 * whenever its music plays (Chromium's AudioFocusDelegate), pauses for a call
 * and plays on after it, turns itself down under a navigation prompt, and
 * stops for good when another app's music starts; the page follows its
 * player either way (desktop/integration.js). Asking for the focus here as
 * well took it from the WebView, which then paused the music it had just
 * started.
 */
object PlaybackGuard {
    private var playing = false
    private var wake: PowerManager.WakeLock? = null
    private var wifi: WifiManager.WifiLock? = null
    private var listening = false

    private val app get() = DannifyApp.instance

    private val headphones = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action == AudioManager.ACTION_AUDIO_BECOMING_NOISY) MediaLink.command("pause")
        }
    }

    /** The page says whether it is playing now (main thread). */
    fun playing(on: Boolean) {
        if (on == playing) return
        playing = on
        listen(on)
        locks(on)
    }

    private fun listen(on: Boolean) {
        if (on == listening) return
        listening = on
        if (on) {
            ContextCompat.registerReceiver(
                app, headphones, IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY),
                ContextCompat.RECEIVER_NOT_EXPORTED,
            )
        } else {
            try { app.unregisterReceiver(headphones) } catch (_: IllegalArgumentException) {}
        }
    }

    @SuppressLint("WakelockTimeout")
    private fun locks(on: Boolean) {
        if (on) {
            if (wake == null) {
                val power = app.getSystemService(Context.POWER_SERVICE) as PowerManager
                wake = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "dannify:playing").apply { setReferenceCounted(false) }
            }
            if (wifi == null) {
                val manager = app.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
                @Suppress("DEPRECATION")
                val mode = if (Build.VERSION.SDK_INT >= 29) WifiManager.WIFI_MODE_FULL_LOW_LATENCY else WifiManager.WIFI_MODE_FULL_HIGH_PERF
                wifi = manager.createWifiLock(mode, "dannify:playing").apply { setReferenceCounted(false) }
            }
            wake?.acquire()
            wifi?.acquire()
        } else {
            wake?.takeIf { it.isHeld }?.release()
            wifi?.takeIf { it.isHeld }?.release()
        }
    }
}
