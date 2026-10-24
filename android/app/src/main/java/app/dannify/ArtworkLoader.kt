package app.dannify

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.annotation.OptIn
import androidx.media3.common.util.BitmapLoader
import androidx.media3.common.util.UnstableApi
import androidx.media3.common.util.Util
import com.google.common.util.concurrent.ListenableFuture
import com.google.common.util.concurrent.MoreExecutors
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/**
 * The cover for the notification and the lock screen. A song's picture is
 * either on YouTube's servers or, for saved songs, served by the backend on
 * 127.0.0.1, which answers only with the app's key.
 */
@OptIn(UnstableApi::class)
class ArtworkLoader : BitmapLoader {
    private val executor = MoreExecutors.listeningDecorator(Executors.newSingleThreadExecutor())

    override fun supportsMimeType(mimeType: String): Boolean = Util.isBitmapFactorySupportedMimeType(mimeType)

    override fun decodeBitmap(data: ByteArray): ListenableFuture<Bitmap> = executor.submit<Bitmap> { decode(data) }

    override fun loadBitmap(uri: Uri): ListenableFuture<Bitmap> = executor.submit<Bitmap> { decode(fetch(uri)) }

    private fun fetch(uri: Uri): ByteArray {
        val connection = URL(uri.toString()).openConnection() as HttpURLConnection
        connection.connectTimeout = 10_000
        connection.readTimeout = 15_000
        if (uri.host == "127.0.0.1") Backend.ready?.let { connection.setRequestProperty("X-Dannify-Key", it.token) }
        try {
            if (connection.responseCode !in 200..299) throw IOException("cover: HTTP ${connection.responseCode}")
            return connection.inputStream.use { it.readBytes() }
        } finally {
            connection.disconnect()
        }
    }

    // Big enough for a lock screen, small enough not to keep 4K covers in
    // memory for a notification.
    private fun decode(data: ByteArray): Bitmap {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(data, 0, data.size, bounds)
        var sample = 1
        while (bounds.outWidth / (sample * 2) >= MAX && bounds.outHeight / (sample * 2) >= MAX) sample *= 2
        val options = BitmapFactory.Options().apply { inSampleSize = sample }
        return BitmapFactory.decodeByteArray(data, 0, data.size, options)
            ?: throw IOException("cover: not a picture")
    }

    private companion object {
        const val MAX = 720
    }
}
