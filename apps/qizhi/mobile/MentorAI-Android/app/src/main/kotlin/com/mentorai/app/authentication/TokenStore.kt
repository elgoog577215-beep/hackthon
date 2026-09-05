package com.mentorai.app.authentication

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * Persists the JWT across launches using `EncryptedSharedPreferences` (AES-256). Mirrors the iOS
 * Keychain-backed token store — read once at app start, written after a successful auth exchange.
 */
class TokenStore(context: Context) {
    private val prefs: SharedPreferences = try {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            FILE_NAME,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    } catch (e: Exception) {
        // Fallback for unsupported devices (e.g. emulators without keystore). Plain prefs is
        // not ideal but lets the app boot; production builds should always succeed above.
        context.getSharedPreferences(FILE_NAME + "_plain", Context.MODE_PRIVATE)
    }

    var accessToken: String?
        get() = prefs.getString(KEY_TOKEN, null)
        set(value) {
            prefs.edit().apply {
                if (value.isNullOrBlank()) remove(KEY_TOKEN) else putString(KEY_TOKEN, value)
            }.apply()
        }

    fun clear() {
        prefs.edit().remove(KEY_TOKEN).apply()
    }

    private companion object {
        const val FILE_NAME = "mentorai_auth"
        const val KEY_TOKEN = "access_token"
    }
}
