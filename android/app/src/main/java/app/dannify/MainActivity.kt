package app.dannify

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.view.Gravity
import android.view.ViewGroup
import android.widget.FrameLayout
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
import kotlinx.coroutines.launch

/**
 * The one screen: the page (see [WebHost]), edge to edge, with the system's
 * bars and the keyboard kept clear of it.
 */
class MainActivity : ComponentActivity() {
    private lateinit var frame: FrameLayout
    private var dark = true

    override fun onCreate(savedInstanceState: Bundle?) {
        val splash = installSplashScreen()
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // Shown until the backend answers (a first start also unpacks it).
        splash.setKeepOnScreenCondition { Backend.state.value is Backend.State.Starting }

        frame = FrameLayout(this).apply { setBackgroundColor(Color.parseColor("#08080A")) }
        setContentView(frame)
        ViewCompat.setOnApplyWindowInsetsListener(frame) { view, insets ->
            val bars = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout() or WindowInsetsCompat.Type.ime()
            )
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            WindowInsetsCompat.CONSUMED
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

    /** The page's theme, so the system's bars match it. */
    fun applyTheme(theme: String) {
        dark = theme != "light"
        WindowCompat.getInsetsController(window, window.decorView).apply {
            isAppearanceLightStatusBars = !dark
            isAppearanceLightNavigationBars = !dark
        }
        frame.setBackgroundColor(Color.parseColor(if (dark) "#08080A" else "#E7E9ED"))
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

    private fun showFailure() {
        if (frame.childCount > 1) return
        frame.addView(
            TextView(this).apply {
                text = getString(R.string.backend_failed)
                setTextColor(Color.WHITE)
                textSize = 16f
                gravity = Gravity.CENTER
                setPadding(64, 64, 64, 64)
                setBackgroundColor(Color.parseColor("#08080A"))
            },
            FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT),
        )
    }
}
