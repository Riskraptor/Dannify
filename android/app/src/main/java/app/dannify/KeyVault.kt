package app.dannify

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.util.Log
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Where the backend keeps the key that protects the music's own key
 * (Backend/dannify/keystore.py, the "android" store): sealed with a key that
 * lives in the phone's Keystore, often in its secure hardware, and never
 * leaves it. Python calls [get] and [put] by name.
 */
object KeyVault {
    private const val ALIAS = "dannify-store-wrap"
    private const val PREFS = "dannify-vault"
    private const val VALUE = "value"

    @JvmStatic
    fun get(): String? {
        val stored = prefs().getString(VALUE, null) ?: return null
        return try {
            val raw = Base64.decode(stored, Base64.NO_WRAP)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, raw.copyOfRange(0, 12)))
            String(cipher.doFinal(raw, 12, raw.size - 12), Charsets.UTF_8)
        } catch (e: Exception) {
            Log.w("Dannify", "the key vault could not be opened", e)
            null
        }
    }

    @JvmStatic
    fun put(value: String): Boolean = try {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val sealed = cipher.iv + cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        prefs().edit().putString(VALUE, Base64.encodeToString(sealed, Base64.NO_WRAP)).commit()
    } catch (e: Exception) {
        Log.w("Dannify", "the key vault could not be written", e)
        false
    }

    private fun prefs() = DannifyApp.instance.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return generator.generateKey()
    }
}
