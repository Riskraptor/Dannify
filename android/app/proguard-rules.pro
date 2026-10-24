# Python calls these by name (Backend/dannify/keystore.py): kept as they are.
-keep class app.dannify.KeyVault { *; }

# The page calls these (frontend/src/desktop/bridge.js).
-keepclassmembers class app.dannify.WebBridge {
    @android.webkit.JavascriptInterface <methods>;
}
