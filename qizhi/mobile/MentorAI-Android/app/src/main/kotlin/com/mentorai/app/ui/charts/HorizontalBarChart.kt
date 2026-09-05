package com.mentorai.app.ui.charts

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.ceil

/**
 * Horizontal bar chart with a left category axis and a bottom value axis (rounded up to a "nice"
 * max). Used for the 语言精炼度 filler-word counts. Mirrors iOS `HorizontalBarChart`.
 */
@Composable
fun HorizontalBarChart(items: List<Pair<String, Int>>, modifier: Modifier = Modifier) {
    val measurer = rememberTextMeasurer()
    val labelStyle = TextStyle(fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurface)
    val axisStyle = TextStyle(fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)

    val rawMax = items.maxOfOrNull { it.second } ?: 1
    val step = niceStep(rawMax)
    val niceMax = maxOf(step, ceil(rawMax.toDouble() / step).toInt() * step)
    val ticks = (0..niceMax step step).toList()

    Canvas(
        modifier = modifier
            .fillMaxWidth()
            .height((items.size * 40 + 24).dp),
    ) {
        val labelWidth = 50.dp.toPx()
        val axisHeight = 20.dp.toPx()
        val plotLeft = labelWidth
        val plotRight = size.width - 6.dp.toPx()
        val plotWidth = (plotRight - plotLeft).coerceAtLeast(1f)
        val plotTop = 4.dp.toPx()
        val plotBottom = size.height - axisHeight
        val rowHeight = ((plotBottom - plotTop) / items.size.coerceAtLeast(1)).coerceAtLeast(1f)
        val barHeight = (rowHeight * 0.55f).coerceAtMost(22.dp.toPx())

        fun xFor(value: Double): Float = plotLeft + plotWidth * (value / niceMax).toFloat()

        for (tick in ticks) {
            val gx = xFor(tick.toDouble())
            drawLine(
                color = Color.Gray.copy(alpha = if (tick == 0) 0.35f else 0.16f),
                start = Offset(gx, plotTop),
                end = Offset(gx, plotBottom),
                strokeWidth = 1f,
            )
            val layout = measurer.measure(tick.toString(), axisStyle)
            drawText(textLayoutResult = layout, topLeft = Offset(gx - layout.size.width / 2f, plotBottom + 4.dp.toPx()))
        }

        items.forEachIndexed { index, (label, value) ->
            val cy = plotTop + rowHeight * (index + 0.5f)
            val layout = measurer.measure(label, labelStyle)
            drawText(
                textLayoutResult = layout,
                topLeft = Offset(plotLeft - 10.dp.toPx() - layout.size.width, cy - layout.size.height / 2f),
            )
            val w = plotWidth * (value.toDouble() / niceMax).toFloat()
            drawRoundRect(
                color = ReportPalette.Primary,
                topLeft = Offset(plotLeft, cy - barHeight / 2f),
                size = Size(w.coerceAtLeast(0f), barHeight),
                cornerRadius = CornerRadius(2.dp.toPx(), 2.dp.toPx()),
            )
        }
    }
}

/** Tick spacing chosen so the axis has roughly 5–6 labels. */
private fun niceStep(value: Int): Int = when {
    value <= 10 -> 2
    value <= 30 -> 5
    value <= 60 -> 10
    value <= 150 -> 25
    else -> 50
}
