package app.dannify

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import androidx.activity.ComponentActivity
import androidx.activity.enableEdgeToEdge
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.webkit.ProfileStore
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import org.json.JSONObject

/**
 * Google's own sign-in page, as on the desktop (Backend/dannify/shell/
 * <system>/login.py): the app never sees a password. Once Google lands on YouTube
 * Music, the session's cookies are read and handed to the backend, which
 * keeps them as the desktop does.
 *
 * Where the phone's WebView allows it, the page has storage of its own (a
 * profile), so signing out wipes it completely and nothing of Google's
 * reaches the app's own page.
 */
class SignInActivity : ComponentActivity() {
    private var web: WebView? = null
    private var delivered = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val frame = FrameLayout(this).apply { setBackgroundColor(Color.WHITE) }
        setContentView(frame)
        ViewCompat.setOnApplyWindowInsetsListener(frame) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            WindowInsetsCompat.CONSUMED
        }
        val view = WebView(this)
        if (WebViewFeature.isFeatureSupported(WebViewFeature.MULTI_PROFILE)) {
            ProfileStore.getInstance().getOrCreateProfile(PROFILE)
            WebViewCompat.setProfile(view, PROFILE)
        }
        view.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            // The phone's own Chrome, as Google expects to see it: an
            // in-app page says so in its name, and Google turns it away.
            userAgentString = userAgentString.replace("; wv)", ")").replace(Regex("""Version/\S+ """), "")
        }
        cookies().setAcceptThirdPartyCookies(view, true)
        view.webViewClient = object : WebViewClient() {
            override fun onPageFinished(page: WebView, url: String) {
                val host = android.net.Uri.parse(url).host ?: return
                if (host == "music.youtube.com" || host == "www.youtube.com") collect()
            }
        }
        frame.addView(view, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        web = view
        view.loadUrl(LOGIN_URL)
    }

    private fun collect() {
        val raw = cookies().getCookie(ORIGIN) ?: return
        val found = JSONObject()
        for (part in raw.split(';')) {
            val cut = part.indexOf('=')
            if (cut <= 0) continue
            val name = part.substring(0, cut).trim()
            val value = part.substring(cut + 1).trim()
            if (value.isNotEmpty()) found.put(name, value)
        }
        // The session is still settling until Google has set these.
        if (!found.has("__Secure-3PAPISID") && !found.has("SAPISID")) return
        deliver(found)
        finish()
    }

    private fun deliver(cookies: JSONObject?) {
        if (delivered) return
        delivered = true
        val done = pending
        pending = null
        done?.invoke(cookies)
    }

    override fun onDestroy() {
        // Closed without signing in.
        deliver(null)
        web?.destroy()
        web = null
        super.onDestroy()
    }

    companion object {
        private const val PROFILE = "google-sign-in"
        private const val ORIGIN = "https://music.youtube.com"
        private const val LOGIN_URL =
            "https://accounts.google.com/ServiceLogin?service=youtube&continue=https%3A%2F%2Fmusic.youtube.com%2F"

        private var pending: ((JSONObject?) -> Unit)? = null

        fun start(done: (JSONObject?) -> Unit) {
            pending?.invoke(null)
            pending = done
            val from: android.content.Context = WebHost.activity ?: DannifyApp.instance
            val intent = Intent(from, SignInActivity::class.java)
            if (from !is Activity) intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            from.startActivity(intent)
        }

        /** Sign-out: everything Google's page kept, gone. */
        fun clearSession(done: (Boolean) -> Unit) {
            if (WebViewFeature.isFeatureSupported(WebViewFeature.MULTI_PROFILE)) {
                val store = ProfileStore.getInstance()
                store.getProfile(PROFILE)?.cookieManager?.removeAllCookies { done(true) } ?: done(true)
                return
            }
            // One cookie jar for the whole app: only Google's go, by expiring
            // each of them; the app's own page keeps its session.
            val manager = CookieManager.getInstance()
            for (site in listOf("https://music.youtube.com", "https://www.youtube.com", "https://accounts.google.com", "https://www.google.com")) {
                val raw = manager.getCookie(site) ?: continue
                for (part in raw.split(';')) {
                    val name = part.substringBefore('=').trim()
                    if (name.isEmpty()) continue
                    for (domain in listOf(".youtube.com", ".google.com", "")) {
                        val where = if (domain.isEmpty()) "" else "; Domain=$domain"
                        manager.setCookie(site, "$name=; Max-Age=0; Path=/$where")
                    }
                }
            }
            manager.flush()
            done(true)
        }

        private fun cookies(): CookieManager =
            if (WebViewFeature.isFeatureSupported(WebViewFeature.MULTI_PROFILE)) {
                ProfileStore.getInstance().getOrCreateProfile(PROFILE).cookieManager
            } else {
                CookieManager.getInstance()
            }
    }
}
