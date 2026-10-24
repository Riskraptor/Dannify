package app.dannify

import android.app.PendingIntent
import android.content.Intent
import android.os.Looper
import androidx.annotation.OptIn
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.DefaultMediaNotificationProvider
import androidx.media3.session.MediaSession
import androidx.media3.session.MediaSessionService

/**
 * The media session: the notification with the song and its buttons, the
 * lock screen, headsets, cars and watches. Media3 keeps the service in the
 * foreground for as long as the music plays, which is also what keeps the
 * app (and the page playing the music) alive with the screen off.
 */
@OptIn(UnstableApi::class)
class PlaybackService : MediaSessionService() {
    private var session: MediaSession? = null

    override fun onCreate() {
        super.onCreate()
        val player = WebPlayer(Looper.getMainLooper())
        val open = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        session = MediaSession.Builder(this, player)
            .setSessionActivity(open)
            .setBitmapLoader(ArtworkLoader())
            .build()
        setMediaNotificationProvider(
            DefaultMediaNotificationProvider.Builder(this).build().apply {
                setSmallIcon(R.drawable.ic_stat_dannify)
            }
        )
        MediaLink.attach(player)
    }

    override fun onGetSession(controllerInfo: MediaSession.ControllerInfo): MediaSession? = session

    override fun onTaskRemoved(rootIntent: Intent?) {
        // Swiped away from the recent apps while paused: nothing to keep the
        // notification for. While playing, the music goes on.
        if (!MediaLink.snapshot.playing) stopSelf()
    }

    override fun onDestroy() {
        session?.let { s ->
            (s.player as? WebPlayer)?.let { MediaLink.detach(it) }
            s.player.release()
            s.release()
        }
        session = null
        super.onDestroy()
    }
}
