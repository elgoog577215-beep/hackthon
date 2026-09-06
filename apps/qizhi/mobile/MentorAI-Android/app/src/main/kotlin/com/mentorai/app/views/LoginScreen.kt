package com.mentorai.app.views

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.School
import androidx.compose.material.icons.filled.VpnKey
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mentorai.app.LocalAuthService
import com.mentorai.app.R
import com.mentorai.app.app.AppState
import com.mentorai.app.authentication.AppEnvironment
import com.mentorai.app.ui.theme.BrandLoginGradientEnd
import com.mentorai.app.ui.theme.BrandLoginGradientStart

/**
 * Mirrors iOS `LoginView`: deep ZJU-blue gradient background, graduationcap hero, 启智 title,
 * MentorAI subtitle, and a translucent "浙大通行证登录" button that triggers the WebView OAuth flow.
 */
@Composable
fun LoginScreen(appState: AppState) {
    val authService = LocalAuthService.current
    val isAuthenticating by appState.isAuthenticating.collectAsState()
    val loginError by appState.loginError.collectAsState()
    var detailShown by remember { mutableStateOf(false) }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.linearGradient(listOf(BrandLoginGradientStart, BrandLoginGradientEnd))
            )
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .windowInsetsPadding(WindowInsets.systemBars)
                .padding(horizontal = 32.dp, vertical = 40.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            Spacer(modifier = Modifier.height(8.dp))

            Header()

            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                SignInButton(
                    isLoading = isAuthenticating,
                    onClick = {
                        if (!isAuthenticating) appState.signIn(authService)
                    },
                )
                if (AppEnvironment.current.showsSkipLogin) {
                    SkipLoginButton(
                        enabled = !isAuthenticating,
                        onClick = { if (!isAuthenticating) appState.skipLogin() },
                    )
                }
            }

            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                if (loginError != null) {
                    ErrorBanner(text = loginError?.errorDescription ?: stringResource(R.string.login_failed_default)) {
                        detailShown = true
                    }
                }
                Text(
                    text = stringResource(R.string.login_footer),
                    color = Color.White.copy(alpha = 0.6f),
                    textAlign = TextAlign.Center,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }

    if (detailShown && loginError != null) {
        AlertDialog(
            onDismissRequest = {
                detailShown = false
                appState.dismissLoginError()
            },
            confirmButton = {
                TextButton(onClick = {
                    detailShown = false
                    appState.dismissLoginError()
                }) { Text(stringResource(R.string.common_confirm)) }
            },
            title = { Text(stringResource(R.string.login_failed_title)) },
            text = {
                Text(loginError?.errorDescription ?: stringResource(R.string.login_failed_unknown))
            },
        )
    }
}

@Composable
private fun Header() {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(
            modifier = Modifier
                .size(132.dp)
                .background(Color.White.copy(alpha = 0.12f), CircleShape)
                .border(1.dp, Color.White.copy(alpha = 0.18f), CircleShape)
                .padding(24.dp),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                Icons.Filled.School,
                contentDescription = null,
                tint = Color.White,
                modifier = Modifier.size(84.dp),
            )
        }
        Text(
            text = stringResource(R.string.app_name),
            color = Color.White,
            fontFamily = FontFamily.SansSerif,
            fontWeight = FontWeight.Bold,
            fontSize = 40.sp,
        )
        Text(
            text = stringResource(R.string.app_name_en),
            color = Color.White.copy(alpha = 0.55f),
            fontFamily = FontFamily.SansSerif,
            fontWeight = FontWeight.Medium,
            fontSize = 15.sp,
            letterSpacing = 2.sp,
        )
        Text(
            text = stringResource(R.string.login_subtitle),
            color = Color.White.copy(alpha = 0.8f),
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

@Composable
private fun SignInButton(isLoading: Boolean, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(54.dp)
            .background(
                Color.White.copy(alpha = 0.18f),
                RoundedCornerShape(14.dp),
            )
            .border(1.dp, Color.White.copy(alpha = 0.35f), RoundedCornerShape(14.dp))
            .clickable(enabled = !isLoading) { onClick() },
        contentAlignment = Alignment.Center,
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (isLoading) {
                CircularProgressIndicator(
                    color = Color.White,
                    strokeWidth = 2.dp,
                    modifier = Modifier.size(20.dp),
                )
            } else {
                Icon(Icons.Filled.VpnKey, contentDescription = null, tint = Color.White)
            }
            Text(
                text = stringResource(
                    if (isLoading) R.string.login_button_loading else R.string.login_button
                ),
                color = Color.White,
                style = MaterialTheme.typography.titleMedium,
            )
        }
    }
}

/** Test-environment only: skip ZJU passport and sign in as the seeded test user. */
@Composable
private fun SkipLoginButton(enabled: Boolean, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(48.dp)
            .border(1.dp, Color.White.copy(alpha = 0.3f), RoundedCornerShape(14.dp))
            .clickable(enabled = enabled) { onClick() },
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = "暂不登录",
            color = Color.White.copy(alpha = 0.85f),
            fontWeight = FontWeight.Medium,
            style = MaterialTheme.typography.titleSmall,
        )
    }
}

@Composable
private fun ErrorBanner(text: String, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(Color.Red.copy(alpha = 0.32f), RoundedCornerShape(10.dp))
            .clickable { onClick() }
            .padding(12.dp),
        verticalAlignment = Alignment.Top,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Icon(Icons.Filled.Warning, contentDescription = null, tint = Color.White)
        Text(text = text, color = Color.White, style = MaterialTheme.typography.bodySmall)
    }
}
