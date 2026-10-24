package app.dannify

import android.annotation.SuppressLint
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.net.wifi.WifiManager
import android.os.Build
import android.os.PowerManager
import androidx.core.content.ContextCompat

/**
 * Being a good music app while the music plays: it holds the audio focus
 * (a call pauses it, and it comes back after; another app taking over for
 * good pauses it for good), it pauses when the headphones come out, and it
 * keeps the phone and the Wi-Fi awake enough to fetch the next song. All of
 * it only while playing.
 */
object PlaybackGuard {
    private var playing = false
    private var pausedForAWhile = false
    private var focus: AudioFocusRequest? = null
    private var wake: PowerManager.WakeLock? = null
    private var wifi: WifiManager.WifiLock? = null
    private var listening = false

    private val app get() = DannifyApp.instance
    private val audio get() = app.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    private val onFocus = AudioManager.OnAudioFocusChangeListener { change ->
        when (change) {
            AudioManager.AUDIOFOCUS_LOSS -> {
                pausedForAWhile = false
                MediaLink.command("pause")
            }
            AudioManager.AUDIOFOCUS_LOSS_TRANSIENT -> if (playing) {
                pausedForAWhile = true
                MediaLink.command("pause")
            }
            AudioManager.AUDIOFOCUS_GAIN -> if (pausedForAWhile) {
                pausedForAWhile = false
                MediaLink.command("play")
            }
            // A short interruption that only lowers the music (a navigation
            // prompt): Android turns it down by itself.
        }
    }

    private val headphones = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action == AudioManager.ACTION_AUDIO_BECOMING_NOISY) MediaLink.command("pause")
        }
    }

    /** The page says whether it is playing now (main thread). */
    fun playing(on: Boolean) {
        if (on == playing) return
        playing = on
        if (on) {
            pausedForAWhile = false
            requestFocus()
            listen(true)
            locks(true)
        } else {
            // Paused by a call: keep the focus, so it comes back afterwards.
            if (!pausedForAWhile) abandonFocus()
            listen(false)
            locks(false)
        }
    }

    private fun requestFocus() {
        if (Build.VERSION.SDK_INT >= 26) {
            val request = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                        .build()
                )
                .setOnAudioFocusChangeListener(onFocus)
                .setWillPauseWhenDucked(false)
                .build()
            focus = request
            audio.requestAudioFocus(request)
        } else {
            @Suppress("DEPRECATION")
            audio.requestAudioFocus(onFocus, AudioManager.STREAM_MUSIC, AudioManager.AUDIOFOCUS_GAIN)
        }
    }

    private fun abandonFocus() {
        if (Build.VERSION.SDK_INT >= 26) {
            focus?.let { audio.abandonAudioFocusRequest(it) }
            focus = null
        } else {
            @Suppress("DEPRECATION")
            audio.abandonAudioFocus(onFocus)
        }
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
