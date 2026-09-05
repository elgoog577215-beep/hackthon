package com.mentorai.app.authentication

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.LinearLayout
import android.widget.ProgressBar
import androidx.activity.ComponentActivity
import androidx.activity.addCallback

/**
 * Loads the ZJU authorization URL in a WebView and intercepts the redirect to the configured
 * `redirect_uri`. Mirrors the iOS `AuthWebViewController` — non-persistent storage so credentials
 * never carry over between sessions, and we cancel the navigation once the `code` query parameter
 * appears.
 *
 * Input  extras: AUTH_URL (String), REDIRECT_URI (String).
 * Output extras: RESULT_CODE (String), RESULT_STATE (String?), RESULT_ERROR (String?).
 */
class AuthWebViewActivity : ComponentActivity() {

    private lateinit var webView: WebView
    private lateinit var progressBar: ProgressBar
    private lateinit var redirectUri: Uri
    private var resolved = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = "ZJU 通行证登录"

        val authUrl = intent.getStringExtra(EXTRA_AUTH_URL)
        val redirect = intent.getStringExtra(EXTRA_REDIRECT_URI)
        if (authUrl.isNullOrBlank() || redirect.isNullOrBlank()) {
            finishWithError("授权链接无效")
            return
        }
        redirectUri = Uri.parse(redirect)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.WHITE)
        }
        progressBar = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                12,
            )
            max = 100
        }
        webView = WebView(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                1f,
            )
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            // Non-persistent: clear cookies/storage at start so the previous session is not reused.
            android.webkit.CookieManager.getInstance().removeAllCookies(null)
            webViewClient = OAuthClient()
        }
        root.addView(progressBar)
        root.addView(webView)
        setContentView(root)

        onBackPressedDispatcher.addCallback(this) {
            cancelAndFinish()
        }

        webView.loadUrl(authUrl)
    }

    private inner class OAuthClient : WebViewClient() {
        override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
            val url = request?.url ?: return false
            if (matchesRedirect(url)) {
                completeWith(url)
                return true
            }
            return false
        }

        override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
            super.onPageStarted(view, url, favicon)
            progressBar.visibility = View.VISIBLE
        }

        override fun onPageFinished(view: WebView?, url: String?) {
            super.onPageFinished(view, url)
            progressBar.visibility = View.GONE
            // Some IdPs land on the redirect via in-page navigation; double-check by inspecting `url`.
            val parsed = url?.let(Uri::parse) ?: return
            if (matchesRedirect(parsed)) completeWith(parsed)
        }
    }

    private fun matchesRedirect(url: Uri): Boolean {
        if (url.scheme?.equals(redirectUri.scheme, ignoreCase = true) != true) return false
        if (url.host?.equals(redirectUri.host, ignoreCase = true) != true) return false
        val targetPath = redirectUri.path.orEmpty()
        if (targetPath.isNotEmpty() && targetPath != "/" && url.path != targetPath) return false
        return url.queryParameterNames.any { it == "code" || it == "error" }
    }

    private fun completeWith(url: Uri) {
        if (resolved) return
        resolved = true
        val errorParam = url.getQueryParameter("error")
        if (!errorParam.isNullOrBlank()) {
            finishWithError(errorParam)
            return
        }
        val code = url.getQueryParameter("code")
        if (code.isNullOrBlank()) {
            finishWithError("未获取到授权码")
            return
        }
        val data = Intent().apply {
            putExtra(EXTRA_RESULT_CODE, code)
            putExtra(EXTRA_RESULT_STATE, url.getQueryParameter("state"))
        }
        setResult(RESULT_OK, data)
        finish()
    }

    private fun cancelAndFinish() {
        if (resolved) return
        resolved = true
        setResult(RESULT_CANCELED)
        finish()
    }

    private fun finishWithError(message: String) {
        if (resolved) return
        resolved = true
        val data = Intent().apply { putExtra(EXTRA_RESULT_ERROR, message) }
        setResult(RESULT_FIRST_USER, data)
        finish()
    }

    companion object {
        const val EXTRA_AUTH_URL = "auth_url"
        const val EXTRA_REDIRECT_URI = "redirect_uri"
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_RESULT_STATE = "result_state"
        const val EXTRA_RESULT_ERROR = "result_error"
    }
}
