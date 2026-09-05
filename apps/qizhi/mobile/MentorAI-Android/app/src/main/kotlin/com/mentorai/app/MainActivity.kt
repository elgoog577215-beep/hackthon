package com.mentorai.app

import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import com.mentorai.app.app.AppState
import com.mentorai.app.app.AppStateFactory
import com.mentorai.app.app.RootScreen
import com.mentorai.app.authentication.ActivityWebViewLauncher
import com.mentorai.app.authentication.AuthService
import com.mentorai.app.authentication.WebViewLauncher
import com.mentorai.app.ui.theme.MentorAITheme

/** Made available to screens that need to drive a fresh sign-in. */
val LocalAuthService = compositionLocalOf<AuthService> { error("AuthService not provided") }

class MainActivity : ComponentActivity() {

    private lateinit var webViewLauncher: ActivityWebViewLauncher

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Draw under the status / nav bars so the login gradient runs edge-to-edge.
        // Both bars are fully transparent; per-screen `SystemBarsEffect` flips status / nav
        // icon appearance so they stay readable on dark (login) and light (rest) backgrounds.
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.auto(Color.TRANSPARENT, Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.auto(Color.TRANSPARENT, Color.TRANSPARENT),
        )

        // Register the OAuth launcher BEFORE first composition so it's wired up by the time the
        // login button fires (matches the iOS `present` pattern).
        webViewLauncher = ActivityWebViewLauncher(this)
        val app = applicationContext as MentorAIApp
        val authService = AuthService(app.authApi, webViewLauncher)

        setContent {
            MentorAITheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    val appState: AppState = viewModel(factory = AppStateFactory(app))
                    CompositionLocalProvider(LocalAuthService provides authService) {
                        RootScreen(appState = appState)
                    }
                }
            }
        }
    }
}
