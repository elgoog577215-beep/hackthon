package com.mentorai.app.ui

import androidx.compose.runtime.Stable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/**
 * Shared toggle the MainScreen Scaffold reads to decide whether to draw its bottom NavigationBar.
 * Screens pushed inside a tab (chat detail, future detail pages) set `hidden = true` from a
 * DisposableEffect so the tab bar slides out while they're on screen and restores on dispose —
 * the Android equivalent of iOS's `.toolbar(.hidden, for: .tabBar)`.
 */
@Stable
class BottomBarVisibility {
    var hidden by mutableStateOf(false)
}

val LocalBottomBarVisibility = compositionLocalOf<BottomBarVisibility> {
    error("LocalBottomBarVisibility not provided — wrap with MainScreen")
}
