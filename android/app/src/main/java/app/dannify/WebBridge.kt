package app.dannify

import android.content.ClipboardManager
import android.content.Context
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.webkit.JavascriptInterface
import com.chaquo.python.Python
import org.json.JSONArray
import org.json.JSONObject
import kotlin.concurrent.thread
import kotlin.system.exitProcess

/**
 * What the interface asks of the app (frontend/src/desktop/bridge.js): the
 * same calls the desktop window answers, under the same names, so the
 * interface needs to know very little about which one it is in.
 *
 * Quick answers come back at once ([call]); slow ones (signing in,
 * installing an update) come back later through window.__dannifyAndroidReply
 * ([callAsync]). Calls about a desktop window (its size, the tray) have
 * nothing to do on a phone and answer null.
 */
object WebBridge {
    private val main = Handler(Looper.getMainLooper())

    /** A link shared to the app before the page was there to open it. */
    @Volatile var pendingLink: String? = null

    @JavascriptInterface
    fun call(name: String, argsJson: String): String {
        val args = try { JSONArray(argsJson) } catch (_: Exception) { JSONArray() }
        return try {
            when (name) {
                "win_state" -> JSONObject().put("platform", "android").toString()
                "android_take_link" -> {
                    val link = pendingLink
                    pendingLink = null
                    if (link == null) "null" else JSONObject.quote(link)
                }
                "taskbar_playback" -> {
                    args.optJSONObject(0)?.let { MediaLink.update(it) }
                    "null"
                }
                "android_downloads" -> {
                    Downloads.update(args.optJSONObject(0))
                    "null"
                }
                "shell_open_external" -> {
                    val url = args.optString(0)
                    if (url.startsWith("https://") || url.startsWith("http://")) {
                        main.post { WebHost.openOutside(Uri.parse(url)) }
                        "true"
                    } else {
                        "false"
                    }
                }
                "clipboard_read" -> JSONObject.quote(clipboardText())
                "app_set_theme" -> {
                    val theme = args.optString(0)
                    main.post { MainActivity.themeChanged(theme) }
                    "null"
                }
                "app_quit" -> {
                    main.post { quit() }
                    "null"
                }
                "app_restart" -> {
                    main.post { restart() }
                    "true"
                }
                else -> "null"
            }
        } catch (e: Exception) {
            Log.w("Dannify", "the interface's $name failed", e)
            "null"
        }
    }

    @JavascriptInterface
    fun callAsync(id: String, name: String, argsJson: String) {
        val args = try { JSONArray(argsJson) } catch (_: Exception) { JSONArray() }
        when (name) {
            "account_sign_in" -> main.post {
                SignInActivity.start { cookies ->
                    if (cookies == null) {
                        reply(id, JSONObject().put("signed_in", false).put("error", "").toString())
                    } else {
                        // Kept the way the desktop keeps them (account.sign_in).
                        thread(name = "dannify-sign-in") {
                            val answer = Python.getInstance()
                                .getModule("dannify.shell.android.host")
                                .callAttr("sign_in", cookies.toString())
                                .toString()
                            reply(id, answer)
                        }
                    }
                }
            }
            "account_clear_session" -> main.post {
                SignInActivity.clearSession { reply(id, it.toString()) }
            }
            "app_install_update" -> {
                val path = args.optString(0)
                main.post { Installer.install(path) { ok -> reply(id, ok.toString()) } }
            }
            else -> reply(id, "null")
        }
    }

    private fun reply(id: String, json: String) {
        WebHost.evaluate("window.__dannifyAndroidReply && window.__dannifyAndroidReply(${JSONObject.quote(id)}, $json)")
    }

    private fun clipboardText(): String {
        val clipboard = DannifyApp.instance.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val clip = clipboard.primaryClip ?: return ""
        if (clip.itemCount == 0) return ""
        return clip.getItemAt(0).coerceToText(DannifyApp.instance)?.toString() ?: ""
    }

    /** Quit for real: the music stops, the notification goes, the app ends. */
    fun quit() {
        MediaLink.stop()
        WebHost.activity?.finishAndRemoveTask()
        main.postDelayed({ exitProcess(0) }, 300)
    }

    /** Start again in a fresh process (a new language, a repaired library). */
    fun restart() {
        val app = DannifyApp.instance
        val intent = app.packageManager.getLaunchIntentForPackage(app.packageName) ?: return
        intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK or android.content.Intent.FLAG_ACTIVITY_CLEAR_TASK)
        MediaLink.stop()
        app.startActivity(intent)
        main.postDelayed({ exitProcess(0) }, 300)
    }
}
