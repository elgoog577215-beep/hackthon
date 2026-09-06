package com.mentorai.app.app

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.slideInVertically
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ScaffoldDefaults
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.Forum
import androidx.compose.material.icons.filled.VideoLibrary
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.mentorai.app.MentorAIApp
import com.mentorai.app.R
import com.mentorai.app.authentication.AuthSession
import com.mentorai.app.ui.BottomBarVisibility
import com.mentorai.app.ui.LocalBottomBarVisibility
import com.mentorai.app.views.HomeScreen
import com.mentorai.app.views.SessionListScreen
import com.mentorai.app.views.VideoAnalysisListScreen

/** Bottom-nav shell matching iOS `MainTabView`. Chat / Video Analysis / Profile. */
@Composable
fun MainScreen(appState: AppState, session: AuthSession) {
    var selected by rememberSaveable { mutableStateOf(MainTab.Chat) }

    val app = LocalContext.current.applicationContext as MentorAIApp
    val bottomBarVisibility = remember { BottomBarVisibility() }

    CompositionLocalProvider(LocalBottomBarVisibility provides bottomBarVisibility) {
        Scaffold(
            bottomBar = {
                // When hidden → the bar disappears instantly (no exit animation, no residual
                // space) so screens like ChatScreen never see a blank gap at the bottom.
                // When shown again → slide+fade in for a polished return transition.
                AnimatedVisibility(
                    visible = !bottomBarVisibility.hidden,
                    enter = slideInVertically(initialOffsetY = { it }) + fadeIn(),
                    // No exit animation – the bar vanishes immediately so the Scaffold
                    // recalculates its bottom padding on the same frame.
                    exit = androidx.compose.animation.ExitTransition.None,
                ) {
                    NavigationBar {
                        MainTab.values().forEach { tab ->
                            NavigationBarItem(
                                selected = selected == tab,
                                onClick = { selected = tab },
                                icon = { Icon(tab.icon, contentDescription = stringResource(tab.labelRes)) },
                                label = { Text(stringResource(tab.labelRes)) },
                            )
                        }
                    }
                }
            },
            // Each tab has its own inner Scaffold with a TopAppBar that already consumes the
            // status-bar inset. Without this restriction the outer Scaffold would also pad the
            // top, stacking two status-bar heights of empty space above the title.
            contentWindowInsets = ScaffoldDefaults.contentWindowInsets
                .only(WindowInsetsSides.Horizontal + WindowInsetsSides.Bottom),
        ) { padding ->
            // When the bottom bar is hidden, ignore the Scaffold's bottom padding so the
            // content extends all the way to the bottom edge without a blank gap.
            val effectivePadding = if (bottomBarVisibility.hidden) {
                PaddingValues(
                    start = padding.calculateLeftPadding(androidx.compose.ui.unit.LayoutDirection.Ltr),
                    top = padding.calculateTopPadding(),
                    end = padding.calculateRightPadding(androidx.compose.ui.unit.LayoutDirection.Ltr),
                    bottom = 0.dp,
                )
            } else {
                padding
            }
            Box(modifier = Modifier.padding(effectivePadding).fillMaxSize()) {
                when (selected) {
                    MainTab.Chat -> SessionListScreen(appState = appState, session = session, app = app)
                    MainTab.Video -> VideoAnalysisListScreen(appState = appState, app = app)
                    MainTab.Profile -> HomeScreen(appState = appState, app = app)
                }
            }
        }
    }
}

private enum class MainTab(val labelRes: Int, val icon: ImageVector) {
    Chat(R.string.tab_chat, Icons.Filled.Forum),
    Video(R.string.tab_resource_analysis, Icons.Filled.VideoLibrary),
    Profile(R.string.tab_profile, Icons.Filled.AccountCircle),
}

/** Temporary tab body until that module is ported. */
@Composable
private fun PlaceholderTab(title: String) {
    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Text(text = "$title（待接入）", color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
