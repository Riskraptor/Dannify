package app.dannify

import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.enableEdgeToEdge
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.webkit.WebViewCompat
import kotlinx.coroutines.launch

/**
 * The one screen: the page (see [WebHost]), edge to edge, with the system's
 * bars and the keyboard kept clear of it.
 */
class MainActivity : ComponentActivity() {
    private lateinit var frame: FrameLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        val splash = installSplashScreen()
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val oldWebView = webViewToUpdate()
        // Shown until the backend answers (a first start also unpacks it).
        splash.setKeepOnScreenCondition { oldWebView == null && Backend.state.value is Backend.State.Starting }

        frame = FrameLayout(this)
        setContentView(frame)
        // As the page last was: a page kept from before shows at once.
        showTheme()
        ViewCompat.setOnApplyWindowInsetsListener(frame) { view, insets ->
            val bars = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout() or WindowInsetsCompat.Type.ime()
            )
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            WindowInsetsCompat.CONSUMED
        }
        if (oldWebView != null) {
            showMessage(getString(R.string.webview_old), getString(R.string.webview_update)) { openStore(oldWebView) }
            return
        }

        val web = WebHost.obtain(this)
        frame.addView(web, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))

        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                Backend.state.collect { state ->
                    when (state) {
                        is Backend.State.Up -> WebHost.load(state.ready.url)
                        is Backend.State.Failed -> showFailure()
                        Backend.State.Starting -> Unit
                    }
                }
            }
        }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                // The page goes back if it can (a dialog, a page it opened);
                // otherwise the app steps aside, still playing.
                web.evaluateJavascript("window.__dannifyBack ? window.__dannifyBack() : false") { handled ->
                    if (handled != "true") moveTaskToBack(true)
                }
            }
        })

        handleLink(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleLink(intent)
    }

    override fun onDestroy() {
        WebHost.release(this)
        super.onDestroy()
    }

    /** Behind the system's bars, the page's own colour, and their icons
     *  light on dark or dark on light. */
    private fun showTheme() {
        WindowCompat.getInsetsController(window, window.decorView).apply {
            isAppearanceLightStatusBars = !dark
            isAppearanceLightNavigationBars = !dark
        }
        frame.setBackgroundColor(background)
    }

    /**
     * A Spotify or YouTube link shared to Dannify, or opened with it: handed
     * to the page, which opens it the way a pasted link opens.
     */
    private fun handleLink(intent: Intent?) {
        val text = when (intent?.action) {
            Intent.ACTION_SEND -> intent.getStringExtra(Intent.EXTRA_TEXT)
            Intent.ACTION_VIEW -> intent.dataString
            else -> null
        } ?: return
        WebBridge.pendingLink = Regex("""(https?://\S+|spotify:\S+)""").find(text)?.value ?: return
        // The page takes it (android_take_link), now if it is up, or as soon
        // as it is.
        WebHost.evaluate("window.__dannifyOpen && window.__dannifyOpen()")
    }

    private fun showFailure() = showMessage(getString(R.string.backend_failed))

    /** A few words on Dannify's black instead of the page, and a button. */
    private fun showMessage(words: String, button: String? = null, onTap: () -> Unit = {}) {
        if (frame.findViewWithTag<LinearLayout>(MESSAGE) != null) return
        val gap = (24 * resources.displayMetrics.density).toInt()
        val message = LinearLayout(this).apply {
            tag = MESSAGE
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(gap, gap, gap, gap)
            setBackgroundColor(Color.parseColor("#08080A"))
            // Over the page, and taking its taps.
            isClickable = true
            addView(TextView(context).apply {
                text = words
                setTextColor(Color.WHITE)
                textSize = 16f
                gravity = Gravity.CENTER
            })
            if (button != null) {
                addView(
                    Button(context).apply {
                        text = button
                        setOnClickListener { onTap() }
                    },
                    LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                        .apply { topMargin = gap },
                )
            }
        }
        frame.addView(message, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
    }

    /**
     * The WebView's package when it is too old for the interface, or missing
     * (turned off, or never installed): the interface's colours are mixed by
     * the browser (CSS color-mix), which WebView has done since version 111.
     * Null when it is fine.
     */
    private fun webViewToUpdate(): String? {
        val current = try { WebViewCompat.getCurrentWebViewPackage(this) } catch (_: Exception) { null }
            ?: return GOOGLE_WEBVIEW
        val major = current.versionName?.substringBefore('.')?.toIntOrNull() ?: return null
        return if (major < MIN_WEBVIEW) current.packageName else null
    }

    private fun openStore(pkg: String) {
        for (address in listOf("market://details?id=$pkg", "https://play.google.com/store/apps/details?id=$pkg")) {
            try {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(address)))
                return
            } catch (_: ActivityNotFoundException) {
                // no store: the web page next
            }
        }
    }

    companion object {
        private const val MESSAGE = "dannify-message"
        private const val MIN_WEBVIEW = 111
        private const val GOOGLE_WEBVIEW = "com.google.android.webview"

        // The page's theme, kept for as long as the page is.
        private var dark = true
        private var background = Color.parseColor("#08080A")

        /**
         * The page switched to *mode* ('dark' or 'light'). Its palette's own
         * background is read off the page itself: there are several of each.
         */
        fun themeChanged(mode: String) {
            dark = mode != "light"
            background = Color.parseColor(if (dark) "#08080A" else "#E7E9ED")
            (WebHost.activity as? MainActivity)?.showTheme()
            WebHost.evaluate("getComputedStyle(document.body).backgroundColor") { css ->
                parseCss(css)?.let { color ->
                    background = color
                    (WebHost.activity as? MainActivity)?.showTheme()
                }
            }
        }

        // "rgb(8, 8, 10)" as evaluateJavascript hands it back, quoted.
        private fun parseCss(css: String?): Int? {
            val parts = Regex("""\d+""").findAll(css ?: return null).map { it.value.toInt() }.toList()
            if (parts.size < 3) return null
            return Color.rgb(parts[0].coerceIn(0, 255), parts[1].coerceIn(0, 255), parts[2].coerceIn(0, 255))
        }
    }
}
