package app.dannify

import android.content.ComponentName
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import androidx.media3.session.MediaController
import androidx.media3.session.SessionToken
import com.google.common.util.concurrent.ListenableFuture
import org.json.JSONObject

/**
 * What is playing, between the page that plays it and the system that shows
 * it (the notification, the lock screen, a headset's buttons, a watch).
 *
 * The page reports through the same call the desktop's media keys use
 * (desktop/integration.js: setPlaybackState); commands go back through
 * window.__dannifyMedia, as they do from a desktop's media keys.
 */
object MediaLink {
    data class Snapshot(
        val hasTrack: Boolean = false,
        val playing: Boolean = false,
        val title: String = "",
        val artist: String = "",
        val album: String = "",
        val cover: String = "",
        val durationMs: Long = 0,
        val positionMs: Long = 0,
        /** When positionMs was true (SystemClock.elapsedRealtime). */
        val at: Long = 0,
        val key: String = "",
        val hasNext: Boolean = false,
        val nextTitle: String = "",
        val nextArtist: String = "",
    )

    private val main = Handler(Looper.getMainLooper())
    @Volatile var snapshot = Snapshot()
        private set
    private var player: WebPlayer? = null
    private var controller: ListenableFuture<MediaController>? = null

    /** The page says what is playing (any thread). */
    fun update(json: JSONObject) {
        val next = json.optJSONObject("next")
        val fresh = Snapshot(
            hasTrack = json.optBoolean("hasTrack"),
            playing = json.optBoolean("playing"),
            title = json.optString("title"),
            artist = json.optString("artist"),
            album = json.optString("album"),
            cover = json.optString("cover"),
            durationMs = (json.optDouble("duration", 0.0) * 1000).toLong(),
            positionMs = (json.optDouble("position", 0.0) * 1000).toLong(),
            at = SystemClock.elapsedRealtime(),
            key = json.optString("key"),
            hasNext = next != null,
            nextTitle = next?.optString("title") ?: "",
            nextArtist = next?.optString("artist") ?: "",
        )
        main.post {
            snapshot = fresh
            player?.show(fresh)
            PlaybackGuard.playing(fresh.playing)
            if (fresh.hasTrack && controller == null) connect()
        }
    }

    /** The page's process was ended: nothing plays until it is back. */
    fun pageGone() {
        main.post {
            val was = snapshot
            val now = SystemClock.elapsedRealtime()
            val at = was.positionMs + if (was.playing) now - was.at else 0
            snapshot = was.copy(playing = false, positionMs = at, at = now)
            player?.show(snapshot)
            PlaybackGuard.playing(false)
        }
    }

    /** A command for the page: play, pause, toggle, next, prev, seek:<s>. */
    fun command(cmd: String) {
        WebHost.evaluate("window.__dannifyMedia && window.__dannifyMedia(${JSONObject.quote(cmd)})")
    }

    fun attach(player: WebPlayer) {
        this.player = player
        player.show(snapshot)
    }

    fun detach(player: WebPlayer) {
        if (this.player === player) this.player = null
    }

    /** Pause, and let the notification and the service go. */
    fun stop() {
        command("pause")
        PlaybackGuard.playing(false)
        controller?.let { MediaController.releaseFuture(it) }
        controller = null
        val app = DannifyApp.instance
        app.stopService(Intent(app, PlaybackService::class.java))
    }

    // Connecting starts the service that holds the media session; staying
    // connected keeps it for as long as there is something to play.
    private fun connect() {
        val app = DannifyApp.instance
        val token = SessionToken(app, ComponentName(app, PlaybackService::class.java))
        controller = MediaController.Builder(app, token).buildAsync()
    }
}
