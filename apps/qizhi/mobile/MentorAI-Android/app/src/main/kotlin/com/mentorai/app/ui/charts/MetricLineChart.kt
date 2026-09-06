package com.mentorai.app.ui.charts

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * Interactive per-window line chart reused for 语速 (CPM) / 音量 (dB) / 信息密度. Tap or scrub
 * horizontally to inspect a point's time + value. Mirrors iOS `MetricLineChart`.
 */
@Composable
fun MetricLineChart(
    title: String,
    samples: List<Double>,
    unit: String = "",
    fractionDigits: Int = 0,
    totalDuration: Double? = null,
    statsAvg: Double? = null,
    statsMax: Double? = null,
    statsMin: Double? = null,
    modifier: Modifier = Modifier,
) {
    var selectedIndex by remember(samples) { mutableStateOf<Int?>(null) }
    val lo = remember(samples) { samples.minOrNull() ?: 0.0 }
    val hi = remember(samples) { samples.maxOrNull() ?: 1.0 }
    val range = max(0.0001, hi - lo)
    val computedAvg = remember(samples) { if (samples.isEmpty()) 0.0 else samples.average() }
    val average = statsAvg ?: computedAvg
    val shownMax = statsMax ?: hi
    val shownMin = statsMin ?: lo
    val unitSuffix = if (unit.isEmpty()) "" else " $unit"
    fun fmt(v: Double): String = "%.${fractionDigits}f".format(v)

    Column(modifier = modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(title, style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.Medium))
            val idx = selectedIndex
            if (idx != null && idx in samples.indices) {
                Text(
                    "${timeLabel(idx, samples.size, totalDuration)} · ${fmt(samples[idx])}$unitSuffix",
                    style = MaterialTheme.typography.labelSmall,
                    color = ReportPalette.Primary,
                )
            } else {
                Text(
                    "平均 ${fmt(average)} · 高 ${fmt(shownMax)} · 低 ${fmt(shownMin)}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        Canvas(
            modifier = Modifier
                .fillMaxWidth()
                .height(150.dp)
                .pointerInput(samples) {
                    detectTapGestures { offset ->
                        if (samples.size > 1 && size.width > 0) {
                            val ratio = (offset.x / size.width).coerceIn(0f, 1f)
                            selectedIndex = (ratio * (samples.size - 1)).roundToInt()
                        }
                    }
                }
                .pointerInput(samples) {
                    detectHorizontalDragGestures(
                        onDragStart = { offset ->
                            if (samples.size > 1 && size.width > 0) {
                                val ratio = (offset.x / size.width).coerceIn(0f, 1f)
                                selectedIndex = (ratio * (samples.size - 1)).roundToInt()
                            }
                        },
                        onHorizontalDrag = { change, _ ->
                            if (samples.size > 1 && size.width > 0) {
                                val ratio = (change.position.x / size.width).coerceIn(0f, 1f)
                                selectedIndex = (ratio * (samples.size - 1)).roundToInt()
                            }
                        },
                    )
                },
        ) {
            if (samples.size <= 1) return@Canvas
            val width = size.width
            val height = size.height

            fun point(index: Int): Offset {
                val x = width * index / (samples.size - 1).toFloat()
                val normalized = ((samples[index] - lo) / range).toFloat()
                return Offset(x, height - normalized * height)
            }

            for (fraction in listOf(0f, 0.5f, 1f)) {
                val y = height * fraction
                drawLine(Color.Gray.copy(alpha = 0.1f), Offset(0f, y), Offset(width, y), strokeWidth = 1f)
            }

            val line = Path()
            for (index in samples.indices) {
                val p = point(index)
                if (index == 0) line.moveTo(p.x, p.y) else line.lineTo(p.x, p.y)
            }
            drawPath(line, color = ReportPalette.Primary, style = Stroke(width = 2f))

            val averageNormalized = ((average - lo) / range).toFloat()
            val averageY = height - averageNormalized * height
            drawLine(
                color = ReportPalette.Average,
                start = Offset(0f, averageY),
                end = Offset(width, averageY),
                strokeWidth = 1.5f,
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(5f, 5f)),
            )

            val idx = selectedIndex
            if (idx != null && idx in samples.indices) {
                val p = point(idx)
                drawLine(
                    color = ReportPalette.Primary.copy(alpha = 0.4f),
                    start = Offset(p.x, 0f),
                    end = Offset(p.x, height),
                    strokeWidth = 1f,
                )
                drawCircle(color = ReportPalette.Primary, radius = 4.dp.toPx(), center = p)
            }
        }
    }
}

private fun timeLabel(index: Int, sampleCount: Int, duration: Double?): String {
    if (duration != null && duration > 0 && sampleCount > 1) {
        return reportClock(duration * index / (sampleCount - 1))
    }
    return "#${index + 1}"
}
