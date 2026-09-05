package com.mentorai.app.ui.charts

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.mentorai.app.videoanalysis.ChartSlice
import kotlin.math.PI
import kotlin.math.atan2
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * 五何互动 / 课堂环节占比 donut chart. Mirrors iOS `DonutChartView`: arc-stroked ring with a
 * tap-to-select that pops the slice and shows centered percent + label; legend chips below.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun DonutChartView(slices: List<ChartSlice>, modifier: Modifier = Modifier) {
    var selectedIndex by remember { mutableStateOf<Int?>(null) }
    val total = remember(slices) { slices.sumOf { it.count }.coerceAtLeast(1) }
    val density = LocalDensity.current
    // Resolve dp → px once so both draw and hit-test agree on geometry.
    val ringWidthPx = with(density) { 26.dp.toPx() }
    val innerPaddingPx = with(density) { 6.dp.toPx() }

    fun percent(count: Int): Int = ((count.toDouble() / total) * 100).roundToInt()

    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Box(modifier = Modifier.fillMaxWidth().height(184.dp), contentAlignment = Alignment.Center) {
            Canvas(
                modifier = Modifier
                    .fillMaxSize()
                    .pointerInput(slices, ringWidthPx) {
                        detectTapGestures { offset ->
                            val center = Offset(size.width / 2f, size.height / 2f)
                            val radius = min(size.width, size.height) / 2f - ringWidthPx / 2f - innerPaddingPx
                            val hit = sliceIndexAt(offset, center, radius, ringWidthPx, slices, total)
                            selectedIndex = if (hit == selectedIndex) null else hit
                        }
                    },
            ) {
                val center = Offset(size.width / 2f, size.height / 2f)
                val radius = min(size.width, size.height) / 2f - ringWidthPx / 2f - innerPaddingPx
                val ringWidth = ringWidthPx

                // Track.
                drawCircle(
                    color = Color.Gray.copy(alpha = 0.12f),
                    radius = radius,
                    center = center,
                    style = Stroke(width = ringWidth),
                )

                var startDeg = -90f
                slices.forEachIndexed { index, slice ->
                    val sweep = (slice.count.toFloat() / total) * 360f
                    val selected = selectedIndex == index
                    val dimmed = selectedIndex != null && !selected
                    val color = ReportPalette.color(index).let { if (dimmed) it.copy(alpha = 0.35f) else it }
                    val w = if (selected) ringWidth + 8.dp.toPx() else ringWidth
                    drawArc(
                        color = color,
                        startAngle = startDeg,
                        sweepAngle = sweep,
                        useCenter = false,
                        topLeft = Offset(center.x - radius, center.y - radius),
                        size = Size(radius * 2, radius * 2),
                        style = Stroke(width = w),
                    )
                    startDeg += sweep
                }
            }

            val selected = selectedIndex?.let { slices.getOrNull(it) }
            if (selected != null) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        selected.label,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Text(
                        "${percent(selected.count)}%",
                        style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
                    )
                }
            }
        }

        // Legend chips. Tapping a chip toggles the slice selection.
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            slices.forEachIndexed { index, slice ->
                val selected = selectedIndex == index
                Row(
                    modifier = Modifier
                        .clickable { selectedIndex = if (selected) null else index }
                        .padding(horizontal = 2.dp, vertical = 2.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(5.dp),
                ) {
                    Box(
                        modifier = Modifier
                            .size(8.dp)
                            .background(ReportPalette.color(index), CircleShape),
                    )
                    Text(
                        text = "${slice.label} ${percent(slice.count)}%",
                        style = MaterialTheme.typography.bodySmall,
                        color = if (selected) MaterialTheme.colorScheme.onSurface
                        else MaterialTheme.colorScheme.onSurfaceVariant,
                        fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
                    )
                }
            }
        }
    }
}

private fun sliceIndexAt(
    point: Offset,
    center: Offset,
    radius: Float,
    ringWidthPx: Float,
    slices: List<ChartSlice>,
    total: Int,
): Int? {
    val dx = point.x - center.x
    val dy = point.y - center.y
    val distance = hypot(dx.toDouble(), dy.toDouble())
    val inner = max(0f, radius - ringWidthPx / 2f - 12f)
    val outer = radius + ringWidthPx / 2f + 12f
    if (distance < inner || distance > outer) return null
    var angle = atan2(dy.toDouble(), dx.toDouble()) + PI / 2
    if (angle < 0) angle += 2 * PI
    val fraction = angle / (2 * PI)
    var cumulative = 0.0
    slices.forEachIndexed { index, slice ->
        val sliceFraction = slice.count.toDouble() / total
        if (fraction >= cumulative && fraction < cumulative + sliceFraction) return index
        cumulative += sliceFraction
    }
    return null
}
