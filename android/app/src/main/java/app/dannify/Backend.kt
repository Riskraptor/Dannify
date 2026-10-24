package app.dannify

import android.content.Context
import android.content.pm.PackageInfo
import android.os.Build
import android.os.Environment
import android.util.Log
import com.chaquo.python.Python
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.json.JSONObject
import java.io.File
import java.util.Locale
import java.util.TimeZone
import kotlin.concurrent.thread

/**
 * The backend (Backend/dannify, run by Chaquopy) on the phone itself: started
 * once per process, on its own thread, through dannify/shell/android/host.py.
 * The interface is served from it on 127.0.0.1, behind a key only this app
 * holds: any app on a phone can reach 127.0.0.1, none of them can use it.
 */
object Backend {
    /** Where the interface is once the backend answers; null until then. */
    data class Ready(val url: String, val base: String, val token: String)

    sealed interface State {
        data object Starting : State
        data class Up(val ready: Ready) : State
        data class Failed(val reason: String) : State
    }

    private val _state = MutableStateFlow<State>(State.Starting)
    val state: StateFlow<State> = _state

    /** The address and key, for the parts of the app that ask the backend
     *  for something themselves (the media notification's pictures). */
    val ready: Ready? get() = (_state.value as? State.Up)?.ready

    @Volatile private var started = false

    fun start(context: Context) {
        if (started) return
        started = true
        val app = context.applicationContext
        thread(name = "dannify-backend", isDaemon = true) {
            _state.value = try {
                unpackInterface(app)
                val answer = JSONObject(
                    Python.getInstance()
                        .getModule("dannify.shell.android.host")
                        .callAttr("start", config(app).toString())
                        .toString()
                )
                if (answer.optBoolean("ok")) {
                    val port = answer.getInt("port")
                    State.Up(Ready(answer.getString("url"), "http://127.0.0.1:$port", answer.getString("token")))
                } else {
                    State.Failed("the backend did not answer")
                }
            } catch (e: Throwable) {
                Log.e("Dannify", "the backend could not start", e)
                State.Failed(e.message ?: e.javaClass.simpleName)
            }
        }
    }

    /** The folders and the locale the backend is told about (host.py). */
    private fun config(app: Context): JSONObject {
        // Saved music: the app's own folder on the phone's storage. It needs
        // no permission, and it goes with the app.
        val music = File(app.getExternalFilesDir(Environment.DIRECTORY_MUSIC) ?: app.filesDir, "Dannify")
        val locale = Locale.getDefault()
        return JSONObject()
            .put("data_dir", File(app.filesDir, "data").path)
            .put("music_dir", music.path)
            .put("bundle_dir", File(app.filesDir, "bundle").path)
            .put("native_dir", app.applicationInfo.nativeLibraryDir)
            .put("cache_dir", app.cacheDir.path)
            .put("time_zone", TimeZone.getDefault().id)
            .put("locale", "${locale.language}_${locale.country}.UTF-8")
            .put("abi", Build.SUPPORTED_ABIS.firstOrNull() ?: "")
    }

    /**
     * The packed interface (assets/dannify.res) as a file the backend can
     * read, copied again only when the app has been updated.
     */
    private fun unpackInterface(app: Context) {
        val folder = File(app.filesDir, "bundle").apply { mkdirs() }
        val target = File(folder, "dannify.res")
        val stamp = File(folder, "version")
        val version = versionOf(app)
        if (target.isFile && stamp.isFile && stamp.readText() == version) return
        val partial = File(folder, "dannify.res.part")
        app.assets.open("dannify.res").use { input -> partial.outputStream().use { input.copyTo(it) } }
        if (!partial.renameTo(target)) {
            target.delete()
            partial.renameTo(target)
        }
        stamp.writeText(version)
    }

    private fun versionOf(app: Context): String {
        val info: PackageInfo = app.packageManager.getPackageInfo(app.packageName, 0)
        @Suppress("DEPRECATION")
        val code = if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong()
        return "$code:${info.lastUpdateTime}"
    }
}
