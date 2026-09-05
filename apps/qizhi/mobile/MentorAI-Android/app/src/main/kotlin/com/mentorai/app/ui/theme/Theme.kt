package com.mentorai.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.mentorai.app.R

// Brand palette — matches the iOS AccentColor / login gradient.
val BrandAccent = Color(0xFF0072BC)
val BrandLoginGradientStart = Color(0xFF002E73)
val BrandLoginGradientEnd = Color(0xFF005CB0)
val SurfaceSecondary = Color(0xFFF2F2F7)

private val LightColors = lightColorScheme(
    primary = BrandAccent,
    onPrimary = Color.White,
    secondary = BrandAccent,
    onSecondary = Color.White,
    background = Color(0xFFF7F7FA),
    onBackground = Color.Black,
    surface = Color.White,
    onSurface = Color.Black,
    surfaceVariant = SurfaceSecondary,
    onSurfaceVariant = Color(0xFF3C3C43),
    error = Color(0xFFD32F2F),
    onError = Color.White,
)

private val DarkColors = darkColorScheme(
    primary = BrandAccent,
    onPrimary = Color.White,
    secondary = BrandAccent,
    onSecondary = Color.White,
    background = Color(0xFF0F1115),
    onBackground = Color.White,
    surface = Color(0xFF15171C),
    onSurface = Color.White,
    surfaceVariant = Color(0xFF1F2127),
    onSurfaceVariant = Color(0xFFD0D0D5),
    error = Color(0xFFEF5350),
    onError = Color.White,
)

/**
 * App-wide Chinese font. The four weights we bundle (`res/font/harmony_os_sans_sc_*.ttf`) cover
 * the common reading needs; requests for SemiBold (600) fall to the nearest available weight,
 * so we explicitly use Medium / Bold below instead of relying on the resolver.
 */
val HarmonyOsSansSC: FontFamily = FontFamily(
    Font(R.font.harmony_os_sans_sc_regular, FontWeight.Normal),
    Font(R.font.harmony_os_sans_sc_medium, FontWeight.Medium),
    Font(R.font.harmony_os_sans_sc_bold, FontWeight.Bold),
    Font(R.font.harmony_os_sans_sc_black, FontWeight.Black),
)

/** Material 3 default Typography, with every style re-skinned in HarmonyOS Sans SC. */
private val MentorAITypography: Typography = run {
    val base = Typography()
    val ff = HarmonyOsSansSC
    Typography(
        displayLarge = base.displayLarge.copy(fontFamily = ff),
        displayMedium = base.displayMedium.copy(fontFamily = ff),
        displaySmall = base.displaySmall.copy(fontFamily = ff),
        headlineLarge = base.headlineLarge.copy(fontFamily = ff),
        headlineMedium = base.headlineMedium.copy(fontFamily = ff),
        headlineSmall = base.headlineSmall.copy(fontFamily = ff),
        titleLarge = base.titleLarge.copy(fontFamily = ff, fontSize = 22.sp, fontWeight = FontWeight.Medium),
        titleMedium = base.titleMedium.copy(fontFamily = ff, fontSize = 18.sp, fontWeight = FontWeight.Medium),
        titleSmall = base.titleSmall.copy(fontFamily = ff),
        bodyLarge = base.bodyLarge.copy(fontFamily = ff, fontSize = 16.sp),
        bodyMedium = base.bodyMedium.copy(fontFamily = ff, fontSize = 14.sp),
        bodySmall = base.bodySmall.copy(fontFamily = ff, fontSize = 12.sp),
        labelLarge = base.labelLarge.copy(fontFamily = ff, fontSize = 15.sp, fontWeight = FontWeight.Medium),
        labelMedium = base.labelMedium.copy(fontFamily = ff),
        labelSmall = base.labelSmall.copy(fontFamily = ff),
    )
}

@Composable
fun MentorAITheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val colors = if (darkTheme) DarkColors else LightColors
    MaterialTheme(
        colorScheme = colors,
        typography = MentorAITypography,
        content = content,
    )
}
