package com.mentorai.app.authentication

import android.app.Activity
import android.content.Context
import android.content.Intent
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import com.mentorai.app.networking.APIClient
import com.mentorai.app.networking.AuthError
import kotlinx.coroutines.CompletableDeferred
import java.net.URLDecoder

/**
 * High-level orchestrator that mirrors the iOS `AuthService.run`:
 *   1. Fetch the ZJU authorize URL from the backend.
 *   2. Extract the `redirect_uri` from its query (we need it to know when to intercept).
 *   3. Present the WebView, wait for the intercepted `code` + optional `state`.
 *   4. Exchange the `code` with the backend for a JWT.
 *
 * Construct with `AuthService.live(context)` from any Activity; call `signIn(activity)` to drive
 * the flow. The activity must be a `ComponentActivity` so we can register a result launcher.
 */
class AuthService(
    private val authApi: AuthAPI,
    private val webViewLauncher: WebViewLauncher,
) {
    /** Drive the full sign-in flow. Returns the JWT on success; throws `AuthError` otherwise. */
    suspend fun signIn(): AuthSession {
        val authUrl = authApi.authorizationUrl()
        val redirectUri = extractRedirectUri(authUrl) ?: throw AuthError.InvalidAuthURL
        val result = webViewLauncher.launch(authUrl, redirectUri)
        val token = authApi.exchange(result.code)
        return AuthSession(accessToken = token)
    }

    suspend fun signOut(token: String) {
        authApi.logout(token)
    }

    private fun extractRedirectUri(authUrl: String): String? {
        val markers = listOf("redirect_uri=", "redirectUri=", "redirect=")
        for (marker in markers) {
            val idx = authUrl.indexOf(marker, ignoreCase = true)
            if (idx == -1) continue
            val start = idx + marker.length
            val end = authUrl.indexOf('&', start).let { if (it == -1) authUrl.length else it }
            val raw = authUrl.substring(start, end)
            if (raw.isNotBlank()) return runCatching { URLDecoder.decode(raw, "UTF-8") }.getOrDefault(raw)
        }
        return null
    }

    companion object {
        fun live(context: Context, config: AuthConfig = AuthConfig.Default): AuthService {
            val api = AuthAPI(APIClient(config.apiBaseUrl))
            // Caller will set the launcher before calling `signIn`. Provide a default that errors
            // until the activity wires one up.
            return AuthService(api, UnboundWebViewLauncher())
        }
    }
}

/** Result data delivered by the WebView. */
data class WebViewLoginResult(val code: String, val state: String?)

/** Abstraction so non-Android code paths (tests) can stub the WebView round-trip. */
interface WebViewLauncher {
    suspend fun launch(authUrl: String, redirectUri: String): WebViewLoginResult
}

class UnboundWebViewLauncher : WebViewLauncher {
    override suspend fun launch(authUrl: String, redirectUri: String): WebViewLoginResult {
        throw AuthError.Transport("WebView launcher not bound; call AuthService.bindLauncher().")
    }
}

/**
 * Activity-backed launcher. Hold a single instance per Activity; register before `onStart` (i.e.
 * in `onCreate`) so the ActivityResultContract is wired up when the Activity is restored.
 */
class ActivityWebViewLauncher(activity: ComponentActivity) : WebViewLauncher {
    private var pending: CompletableDeferred<WebViewLoginResult>? = null

    private val launcher = activity.registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        val deferred = pending ?: return@registerForActivityResult
        pending = null
        when (result.resultCode) {
            Activity.RESULT_OK -> {
                val code = result.data?.getStringExtra(AuthWebViewActivity.EXTRA_RESULT_CODE)
                if (code.isNullOrBlank()) {
                    deferred.completeExceptionally(AuthError.MissingAuthorizationCode)
                } else {
                    deferred.complete(
                        WebViewLoginResult(
                            code = code,
                            state = result.data?.getStringExtra(AuthWebViewActivity.EXTRA_RESULT_STATE),
                        )
                    )
                }
            }
            Activity.RESULT_CANCELED -> deferred.completeExceptionally(AuthError.UserCancelled)
            else -> {
                val msg = result.data?.getStringExtra(AuthWebViewActivity.EXTRA_RESULT_ERROR)
                deferred.completeExceptionally(AuthError.Transport(msg ?: "登录失败"))
            }
        }
    }

    private val ctx: Context = activity

    override suspend fun launch(authUrl: String, redirectUri: String): WebViewLoginResult {
        val deferred = CompletableDeferred<WebViewLoginResult>()
        pending = deferred
        val intent = Intent(ctx, AuthWebViewActivity::class.java).apply {
            putExtra(AuthWebViewActivity.EXTRA_AUTH_URL, authUrl)
            putExtra(AuthWebViewActivity.EXTRA_REDIRECT_URI, redirectUri)
        }
        launcher.launch(intent)
        return deferred.await()
    }
}
