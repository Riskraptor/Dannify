package app.dannify

import android.annotation.SuppressLint
import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.MutableContextWrapper
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.ViewGroup
import android.webkit.ConsoleMessage
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import java.lang.ref.WeakReference

/**
 * The one page the app shows, kept for as long as the process lives.
 *
 * It belongs to the app, not to a screen: the activity borrows it while it
 * is on screen and gives it back when it goes. Swiping Dannify away from the
 * recent apps then does not stop the music, and coming back is instant, with
 * the page exactly as it was.
 */
object WebHost {
    private val main = Handler(Looper.getMainLooper())
    private var view: WebView? = null
    private var context: MutableContextWrapper? = null
    private var activityRef: WeakReference<Activity>? = null
    private var loaded: String? = null

    /** The activity showing the page now, if any (for screens it opens). */
    val activity: Activity? get() = activityRef?.get()

    /** The page, made the first time, moved into *activity* every time. */
    fun obtain(activity: Activity): WebView {
        activityRef = WeakReference(activity)
        val existing = view
        if (existing != null) {
            context?.baseContext = activity
            (existing.parent as? ViewGroup)?.removeView(existing)
            return existing
        }
        val wrapper = MutableContextWrapper(activity)
        context = wrapper
        return create(wrapper).also { view = it }
    }

    /** The activity is going: the page stays, on the app's context. */
    fun release(activity: Activity) {
        if (activityRef?.get() === activity) activityRef = null
        val web = view ?: return
        (web.parent as? ViewGroup)?.removeView(web)
        if (context?.baseContext === activity) context?.baseContext = activity.applicationContext
    }

    /** Show the interface at *url* (once: a page already showing it stays). */
    fun load(url: String) {
        val web = view ?: return
        if (loaded == url) return
        loaded = url
        web.loadUrl(url)
    }

    /** Run *script* in the page, from any thread; *done* gets its answer. */
    fun evaluate(script: String, done: ((String?) -> Unit)? = null) {
        main.post {
            val web = view
            if (web == null) done?.invoke(null) else web.evaluateJavascript(script) { done?.invoke(it) }
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun create(wrapper: MutableContextWrapper): WebView {
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        val web = WebView(wrapper)
        web.setBackgroundColor(Color.parseColor("#08080A"))
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            // The music starts from the queue, not only from a tap.
            mediaPlaybackRequiresUserGesture = false
            allowFileAccess = false
            allowContentAccess = false
            javaScriptCanOpenWindowsAutomatically = false
            setSupportMultipleWindows(false)
            // The interface sizes its own text; the system's font scale on
            // top of it broke its layout.
            textZoom = 100
        }
        // The page keeps its priority when it is not on screen: it is
        // playing the music.
        if (Build.VERSION.SDK_INT >= 26) web.setRendererPriorityPolicy(WebView.RENDERER_PRIORITY_IMPORTANT, false)
        web.addJavascriptInterface(WebBridge, "DannifyAndroid")
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val uri = request.url
                // The backend's own pages stay here; everything else (a
                // release page, a support link) opens where it belongs.
                if (uri.host == "127.0.0.1") return false
                openOutside(uri)
                return true
            }

            override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                // The page's process went (memory pressure, a crash): make a
                // new page rather than taking the whole app down with it.
                Log.w("Dannify", "the page's process went; reloading it")
                MediaLink.pageGone()
                val web = this@WebHost.view
                this@WebHost.view = null
                loaded = null
                (web?.parent as? ViewGroup)?.removeView(web)
                web?.destroy()
                activity?.recreate()
                return true
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(message: ConsoleMessage): Boolean {
                if (BuildConfig.DEBUG) Log.d("DannifyPage", "${message.message()} (${message.sourceId()}:${message.lineNumber()})")
                return true
            }
        }
        return web
    }

    fun openOutside(uri: Uri) {
        val from = activity ?: DannifyApp.instance
        val intent = Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        try {
            from.startActivity(intent)
        } catch (_: ActivityNotFoundException) {
            Log.w("Dannify", "nothing on this phone opens $uri")
        }
    }
}
