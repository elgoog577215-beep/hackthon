package com.mentorai.app.ui.charts

import androidx.compose.ui.graphics.Color

/**
 * Mirrors the iOS `ReportPalette` and the web report colors. Used by every chart in the
 * video-analysis detail screen so the visuals match across platforms.
 */
object ReportPalette {
    val Primary = Color(0xFF5B8DEE)
    val Average = Color(0xFFE8B84D)

    val Series: List<Color> = listOf(
        Color(0xFF5B8DEE), // blue
        Color(0xFF67C23A), // green
        Color(0xFFE8B84D), // gold
        Color(0xFFE36B6B), // red
        Color(0xFF9B7BEA), // purple
        Color(0xFF4DBFB5), // teal
        Color(0xFFF09B59), // orange
    )

    fun color(index: Int): Color = Series[((index % Series.size) + Series.size) % Series.size]

    /** Green / amber / red by score band (mirrors the web's score-high/mid/low). */
    fun scoreColor(score: Int): Color = when {
        score >= 80 -> Color(0xFF40B55E)
        score >= 60 -> Color(0xFFE8B84D)
        else -> Color(0xFFE36B6B)
    }

    private val InteractionTypeOrder = listOf("记忆型", "理解型", "应用型", "分析型", "评价型", "创新型")

    /** Stable color for an interaction 题型. */
    fun interactionTypeColor(type: String): Color {
        val index = InteractionTypeOrder.indexOf(type)
        return if (index >= 0) color(index) else Primary
    }
}

/** Word-cloud color set — slightly broader, matches the iOS hex list. */
val WordCloudPalette: List<Color> = listOf(
    Color(0xFF1358E4), Color(0xFF5B8DEE), Color(0xFFE06B5A), Color(0xFFF2B84B),
    Color(0xFF5FD3B3), Color(0xFF6B5FE3), Color(0xFFF28ADC), Color(0xFF4BC0C0),
    Color(0xFFFFA07A), Color(0xFF20B2AA), Color(0xFF9370DB), Color(0xFFFFB347),
    Color(0xFFA0D468), Color(0xFFE7C14A),
)

/** Formats seconds as "H:MM:SS" or "M:SS" — matches iOS `ReportFormat.clock`. */
fun reportClock(seconds: Double): String {
    val total = seconds.toInt()
    val h = total / 3600
    val m = (total % 3600) / 60
    val s = total % 60
    return if (h > 0) "%d:%02d:%02d".format(h, m, s) else "%d:%02d".format(m, s)
}
