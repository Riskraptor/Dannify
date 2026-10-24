package app.dannify

import android.net.Uri
import android.os.Looper
import android.os.SystemClock
import androidx.annotation.OptIn
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import androidx.media3.common.SimpleBasePlayer
import androidx.media3.common.util.UnstableApi
import com.google.common.util.concurrent.Futures
import com.google.common.util.concurrent.ListenableFuture

/**
 * The page's player as Media3 sees one: it plays nothing itself. What it
 * shows comes from [MediaLink.snapshot]; what it is asked to do goes to the
 * page. The song before and after the one playing are listed around it, so
 * the notification and headsets offer next and previous.
 */
@OptIn(UnstableApi::class)
class WebPlayer(looper: Looper) : SimpleBasePlayer(looper) {
    private var shown = MediaLink.Snapshot()
    private var currentIndex = 0

    fun show(snapshot: MediaLink.Snapshot) {
        shown = snapshot
        invalidateState()
    }

    override fun getState(): State {
        val s = shown
        val commands = Player.Commands.Builder()
            .addAll(
                COMMAND_PLAY_PAUSE,
                COMMAND_STOP,
                COMMAND_SEEK_IN_CURRENT_MEDIA_ITEM,
                COMMAND_SEEK_TO_PREVIOUS,
                COMMAND_SEEK_TO_PREVIOUS_MEDIA_ITEM,
                COMMAND_SEEK_TO_NEXT,
                COMMAND_SEEK_TO_NEXT_MEDIA_ITEM,
                COMMAND_SEEK_TO_MEDIA_ITEM,
                COMMAND_GET_CURRENT_MEDIA_ITEM,
                COMMAND_GET_TIMELINE,
                COMMAND_GET_METADATA,
            )
            .build()
        val builder = State.Builder().setAvailableCommands(commands)
        if (!s.hasTrack) {
            return builder
                .setPlaybackState(STATE_IDLE)
                .setPlayWhenReady(false, PLAY_WHEN_READY_CHANGE_REASON_USER_REQUEST)
                .build()
        }
        val items = mutableListOf<MediaItemData>()
        // Previous is always there: it starts the song again or goes back.
        items += placeholder("previous", "", "")
        currentIndex = items.size
        val metadata = MediaMetadata.Builder()
            .setTitle(s.title)
            .setArtist(s.artist)
            .setAlbumTitle(s.album.ifEmpty { null })
            .setArtworkUri(artwork(s.cover))
            .setIsPlayable(true)
            .build()
        items += MediaItemData.Builder("now:${s.key}")
            .setMediaItem(MediaItem.Builder().setMediaId(s.key).setMediaMetadata(metadata).build())
            .setMediaMetadata(metadata)
            .setDurationUs(if (s.durationMs > 0) s.durationMs * 1000 else androidx.media3.common.C.TIME_UNSET)
            .setIsSeekable(s.durationMs > 0)
            .build()
        if (s.hasNext) items += placeholder("next", s.nextTitle, s.nextArtist)
        val position = s.positionMs + if (s.playing) SystemClock.elapsedRealtime() - s.at else 0
        return builder
            .setPlaylist(items)
            .setCurrentMediaItemIndex(currentIndex)
            .setPlayWhenReady(s.playing, PLAY_WHEN_READY_CHANGE_REASON_USER_REQUEST)
            .setPlaybackState(STATE_READY)
            .setContentPositionMs(
                if (s.playing) PositionSupplier.getExtrapolating(position, 1f)
                else PositionSupplier.getConstant(position)
            )
            .build()
    }

    private fun placeholder(id: String, title: String, artist: String): MediaItemData {
        val metadata = MediaMetadata.Builder().setTitle(title).setArtist(artist).build()
        return MediaItemData.Builder(id)
            .setMediaItem(MediaItem.Builder().setMediaId(id).setMediaMetadata(metadata).build())
            .setMediaMetadata(metadata)
            .build()
    }

    private fun artwork(cover: String): Uri? {
        if (cover.isEmpty()) return null
        // The backend's own pictures are named from its root.
        val full = if (cover.startsWith("/")) (Backend.ready?.base ?: return null) + cover else cover
        return Uri.parse(full)
    }

    override fun handleSetPlayWhenReady(playWhenReady: Boolean): ListenableFuture<*> {
        MediaLink.command(if (playWhenReady) "play" else "pause")
        shown = shown.copy(playing = playWhenReady, positionMs = positionNow(), at = SystemClock.elapsedRealtime())
        return Futures.immediateVoidFuture()
    }

    override fun handleStop(): ListenableFuture<*> {
        MediaLink.command("pause")
        shown = shown.copy(playing = false, positionMs = positionNow(), at = SystemClock.elapsedRealtime())
        return Futures.immediateVoidFuture()
    }

    override fun handleSeek(mediaItemIndex: Int, positionMs: Long, seekCommand: Int): ListenableFuture<*> {
        when {
            mediaItemIndex > currentIndex -> MediaLink.command("next")
            mediaItemIndex < currentIndex -> MediaLink.command("prev")
            else -> {
                val at = if (positionMs == androidx.media3.common.C.TIME_UNSET) 0 else positionMs
                MediaLink.command("seek:${at / 1000.0}")
                shown = shown.copy(positionMs = at, at = SystemClock.elapsedRealtime())
            }
        }
        return Futures.immediateVoidFuture()
    }

    private fun positionNow(): Long =
        shown.positionMs + if (shown.playing) SystemClock.elapsedRealtime() - shown.at else 0
}
