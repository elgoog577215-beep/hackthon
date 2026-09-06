package com.mentorai.app.ui

import android.app.Activity
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

/**
 * Flips the system status / navigation bar icon appearance to remain readable against the
 * current screen's background. Pair with `enableEdgeToEdge(...)` in MainActivity, which
 * keeps the bars fully transparent so the screen content can draw underneath them.
 *
 * `lightIcons = true` → light-on-dark icons (use on dark gradients, e.g. the login screen).
 * `lightIcons = false` → dark-on-light icons (use on the main shell's white surfaces).
 *
 * Internally we set `isAppearanceLightStatusBars` / `isAppearanceLightNavigationBars`. The
 * AndroidX flag is named for the *background*: `true` means "the bar background is light, so
 * draw dark icons." Hence the inversion.
 */
@Composable
fun SystemBarsEffect(lightIcons: Boolean) {
    val view = LocalView.current
    if (view.isInEditMode) return
    SideEffect {
        val window = (view.context as Activity).window
        val controller = WindowCompat.getInsetsController(window, view)
        controller.isAppearanceLightStatusBars = !lightIcons
        controller.isAppearanceLightNavigationBars = !lightIcons
    }
}
