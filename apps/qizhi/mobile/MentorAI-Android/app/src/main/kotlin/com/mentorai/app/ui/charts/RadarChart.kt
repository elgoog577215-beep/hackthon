package com.mentorai.app.ui.charts

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.foundation.Canvas
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mentorai.app.videoanalysis.RadarAxis
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.sin

/**
 * 雷达图 — six teaching-performance axes scored 0..100. Mirrors iOS `RadarChartView`:
 * draws 5 grid rings + spokes + filled polygon, with tap-to-select that highlights the
 * tapped axis and shows its score in a center pill.
 */
@Composable
fun RadarChartView(axes: List<RadarAxis>, modifier: Modifier = Modifier) {
    val measurer = rememberTextMeasurer()
    var selectedIndex by remember { mutableStateOf<Int?>(null) }

    val labelStyle = TextStyle(fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    val labelStyleSelected = labelStyle.copy(color = ReportPalette.Primary, fontWeight = FontWeight.SemiBold)
    val valueStyle = TextStyle(fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.SemiBold)
    val valueStyleSelected = valueStyle.copy(color = ReportPalette.Primary)

    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(280.dp),
        contentAlignment = Alignment.Center,
    ) {
        Canvas(
            modifier = Modifier
                .fillMaxSize()
                .pointerInput(axes) {
                    detectTapGestures { offset ->
                        val center = Offset(size.width / 2f, size.height / 2f)
                        selectedIndex = axisIndexAt(offset, center, axes.size).let { hit ->
                            if (hit == selectedIndex) null else hit
                        }
                    }
                },
        ) {
            val count = axes.size
            if (count < 3) return@Canvas
            val center = Offset(size.width / 2f, size.height / 2f)
            val radius = min(size.width, size.height) / 2f - 46.dp.toPx()

            fun vertex(fraction: Double, index: Int): Offset {
                val angle = -PI / 2 + index * 2 * PI / count
                return Offset(
                    x = (center.x + cos(angle) * radius * fraction).toFloat(),
                    y = (center.y + sin(angle) * radius * fraction).toFloat(),
                )
            }

            // Grid rings.
            for (level in 1..5) {
                val grid = Path()
                val fraction = level / 5.0
                for (index in 0 until count) {
                    val p = vertex(fraction, index)
                    if (index == 0) grid.moveTo(p.x, p.y) else grid.lineTo(p.x, p.y)
                }
                grid.close()
                drawPath(grid, color = Color.Gray.copy(alpha = 0.22f), style = Stroke(width = 1f))
            }

            // Spokes.
            for (index in 0 until count) {
                val spoke = Path()
                spoke.moveTo(center.x, center.y)
                val tip = vertex(1.0, index)
                spoke.lineTo(tip.x, tip.y)
                val selected = selectedIndex == index
                drawPath(
                    spoke,
                    color = if (selected) ReportPalette.Primary.copy(alpha = 0.5f) else Color.Gray.copy(alpha = 0.18f),
                    style = Stroke(width = if (selected) 1.5f else 1f),
                )
            }

            // Polygon.
            val shape = Path()
            for (index in 0 until count) {
                val fraction = (axes[index].value / 100.0).coerceIn(0.0, 1.0)
                val p = vertex(fraction, index)
                if (index == 0) shape.moveTo(p.x, p.y) else shape.lineTo(p.x, p.y)
            }
            shape.close()
            drawPath(shape, color = ReportPalette.Primary.copy(alpha = 0.28f))
            drawPath(shape, color = ReportPalette.Primary, style = Stroke(width = 2f))

            // Vertices + labels.
            for (index in 0 until count) {
                val selected = selectedIndex == index
                val fraction = (axes[index].value / 100.0).coerceIn(0.0, 1.0)
                val p = vertex(fraction, index)
                val r = if (selected) 5.dp.toPx() else 3.dp.toPx()
                drawCircle(color = ReportPalette.Primary, radius = r, center = p)

                val labelAnchor = vertex(1.2, index)
                val labelLayout = measurer.measure(axes[index].label, if (selected) labelStyleSelected else labelStyle)
                drawText(
                    textLayoutResult = labelLayout,
                    topLeft = Offset(
                        labelAnchor.x - labelLayout.size.width / 2f,
                        labelAnchor.y - labelLayout.size.height / 2f,
                    ),
                )
                val valueLayout = measurer.measure(
                    axes[index].value.roundToInt().toString(),
                    if (selected) valueStyleSelected else valueStyle,
                )
                drawText(
                    textLayoutResult = valueLayout,
                    topLeft = Offset(
                        labelAnchor.x - valueLayout.size.width / 2f,
                        labelAnchor.y + 13.dp.toPx() - valueLayout.size.height / 2f,
                    ),
                )
            }
        }

        // Center pill — shows the selected axis label + score.
        val selected = selectedIndex?.let { axes.getOrNull(it) }
        AnimatedVisibility(visible = selected != null, enter = fadeIn(), exit = fadeOut()) {
            if (selected != null) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier
                        .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.85f), RoundedCornerShape(20.dp))
                        .padding(horizontal = 10.dp, vertical = 6.dp),
                ) {
                    Text(selected.label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(
                        "${selected.value.roundToInt()} 分",
                        style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
                    )
                }
            }
        }
    }
}

private fun axisIndexAt(tap: Offset, center: Offset, count: Int): Int? {
    if (count < 3) return null
    val dx = tap.x - center.x
    val dy = tap.y - center.y
    if (hypot(dx.toDouble(), dy.toDouble()) < 16f) return null
    val tapAngle = atan2(dy.toDouble(), dx.toDouble())
    var best = 0
    var bestDelta = Double.POSITIVE_INFINITY
    for (index in 0 until count) {
        val axisAngle = -PI / 2 + index * 2 * PI / count
        val delta = abs(angleDelta(tapAngle, axisAngle))
        if (delta < bestDelta) { bestDelta = delta; best = index }
    }
    return best
}

private fun angleDelta(a: Double, b: Double): Double {
    var d = (a - b) % (2 * PI)
    if (d > PI) d -= 2 * PI else if (d < -PI) d += 2 * PI
    return d
}
