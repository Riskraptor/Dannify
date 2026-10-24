package app.dannify

import android.app.Application
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

/**
 * The app as a whole: starts Python and, on a thread of its own, the backend,
 * as soon as the process starts, so the interface is ready as early as it
 * can be. Everything else hangs off the one [WebHost] and [MediaLink].
 */
class DannifyApp : Application() {
    override fun onCreate() {
        super.onCreate()
        instance = this
        if (!Python.isStarted()) Python.start(AndroidPlatform(this))
        Backend.start(this)
    }

    companion object {
        lateinit var instance: DannifyApp
            private set
    }
}
