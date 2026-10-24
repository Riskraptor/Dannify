package app.dannify

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import org.json.JSONObject

/**
 * Songs being saved, kept going while the app is put away: without a
 * foreground service Android may end the app, and the downloads with it, as
 * soon as nobody is looking at it and no music plays. Its notification says
 * how far they have got, in the interface's own words
 * (desktop/integration.js: setDownloads), and goes when they are done.
 */
class DownloadService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val shown = Downloads.notification(this)
        try {
            if (Build.VERSION.SDK_INT >= 29) {
                startForeground(Downloads.ID, shown, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
            } else {
                startForeground(Downloads.ID, shown)
            }
        } catch (e: Exception) {
            // Android would not have it in the foreground right now (the app
            // already put away): the downloads go on for as long as they may.
            Log.w("Dannify", "downloads not kept in the foreground", e)
            stopSelf()
        }
        return START_NOT_STICKY
    }

    // Android 15 gives a data transfer six hours a day in the foreground.
    override fun onTimeout(startId: Int, fgsType: Int) {
        stopSelf()
    }
}

/** What the page says about the songs being saved (main thread). */
object Downloads {
    const val ID = 7
    private const val CHANNEL = "downloads"

    private val main = Handler(Looper.getMainLooper())
    private val app get() = DannifyApp.instance
    private var running = false
    private var text = ""
    private var percent = 0
    private var wake: PowerManager.WakeLock? = null
    private var wifi: WifiManager.WifiLock? = null

    /** {active, percent, text}, or null once every song is saved. */
    fun update(state: JSONObject?) {
        main.post {
            if (state == null || state.optInt("active") <= 0) {
                stop()
                return@post
            }
            text = state.optString("text")
            percent = state.optInt("percent").coerceIn(0, 100)
            if (running) {
                refresh()
            } else {
                start()
            }
        }
    }

    private fun start() {
        running = true
        locks(true)
        try {
            ContextCompat.startForegroundService(app, Intent(app, DownloadService::class.java))
        } catch (e: Exception) {
            Log.w("Dannify", "the downloads' service could not start", e)
        }
        (WebHost.activity as? MainActivity)?.askToNotify()
    }

    private fun refresh() {
        val manager = app.getSystemService(NotificationManager::class.java)
        try {
            manager.notify(ID, notification(app))
        } catch (_: SecurityException) {
            // No permission to show it: the downloads go on regardless.
        }
    }

    private fun stop() {
        if (!running) return
        running = false
        locks(false)
        app.stopService(Intent(app, DownloadService::class.java))
    }

    fun notification(context: Context): Notification {
        val manager = context.getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26 && manager.getNotificationChannel(CHANNEL) == null) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL, context.getString(R.string.downloads_channel), NotificationManager.IMPORTANCE_LOW)
                    .apply { setShowBadge(false) }
            )
        }
        val open = PendingIntent.getActivity(
            context, 1,
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        return NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_dannify)
            .setContentTitle(text)
            .setProgress(100, percent, percent == 0)
            .setContentIntent(open)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .build()
    }

    // Awake enough to keep fetching with the screen off, only while saving.
    @SuppressLint("WakelockTimeout")
    private fun locks(on: Boolean) {
        if (on) {
            if (wake == null) {
                val power = app.getSystemService(Context.POWER_SERVICE) as PowerManager
                wake = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "dannify:saving").apply { setReferenceCounted(false) }
            }
            if (wifi == null) {
                val manager = app.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
                @Suppress("DEPRECATION")
                val mode = if (Build.VERSION.SDK_INT >= 29) WifiManager.WIFI_MODE_FULL_LOW_LATENCY else WifiManager.WIFI_MODE_FULL_HIGH_PERF
                wifi = manager.createWifiLock(mode, "dannify:saving").apply { setReferenceCounted(false) }
            }
            wake?.acquire()
            wifi?.acquire()
        } else {
            wake?.takeIf { it.isHeld }?.release()
            wifi?.takeIf { it.isHeld }?.release()
        }
    }
}
