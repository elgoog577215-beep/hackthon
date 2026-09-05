package com.mentorai.app.app

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.mentorai.app.R
import com.mentorai.app.ui.SystemBarsEffect
import com.mentorai.app.views.LoginScreen

/**
 * Drives the top-level phase switch — Launching → SignedOut (login) → SignedIn (main shell).
 * Mirrors iOS `RootView`.
 */
@Composable
fun RootScreen(appState: AppState) {
    val phase by appState.phase.collectAsState()

    // Login uses a dark ZJU-blue gradient that runs edge-to-edge; everything else sits on
    // light surfaces. Flip system-bar icon appearance accordingly so they stay legible.
    SystemBarsEffect(lightIcons = phase is AppState.Phase.SignedOut)

    AnimatedContent(
        targetState = phase,
        label = "phase",
        transitionSpec = { fadeIn() togetherWith fadeOut() },
    ) { current ->
        when (current) {
            is AppState.Phase.Launching -> SplashView()
            is AppState.Phase.SignedOut -> LoginScreen(appState = appState)
            is AppState.Phase.SignedIn -> MainScreen(appState = appState, session = current.session)
        }
    }
}

@Composable
private fun SplashView() {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            CircularProgressIndicator()
            Text(
                text = stringResource(R.string.splash_loading),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
