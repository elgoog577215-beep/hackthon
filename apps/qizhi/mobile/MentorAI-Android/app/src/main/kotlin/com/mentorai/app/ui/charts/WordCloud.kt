package com.mentorai.app.ui.charts

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.sp
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sin

/**
 * 知识点词云 — Archimedean-spiral word cloud built from teach_knowledge titles. Mirrors the
 * iOS `WordCloudView`: extract 2..6 char hot-word phrases, size by frequency, then place
 * largest-first along a spiral using an occupancy grid to avoid overlaps.
 */
/** Build a cloud from backend-weighted words (`word_cloud: [{word, weight}]`). */
@Composable
fun WordCloudView(words: List<Pair<String, Int>>, modifier: Modifier = Modifier) {
    val placed = remember(words) { placeWords(words) }
    WordCloudCanvas(placed, modifier)
}

@Composable
private fun WordCloudCanvas(placed: List<PlacedWord>, modifier: Modifier = Modifier) {
    val measurer = rememberTextMeasurer()

    if (placed.isEmpty()) {
        Text(
            "暂无数据",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        return
    }

    Canvas(
        modifier = modifier
            .fillMaxWidth()
            .aspectRatio(1f),
    ) {
        val scale = size.width / CANVAS
        for (word in placed) {
            val style = TextStyle(
                // Placement is in pixel space; convert px -> sp so the rendered text matches the
                // reserved slot (using .sp here would density-scale it and cause overlaps).
                fontSize = (word.size * scale).toSp(),
                fontWeight = word.weight,
                color = word.color,
            )
            val layout = measurer.measure(word.text, style)
            drawText(
                textLayoutResult = layout,
                topLeft = Offset(
                    word.center.x * scale - layout.size.width / 2f,
                    word.center.y * scale - layout.size.height / 2f,
                ),
            )
        }
    }
}

// -------- layout --------

private const val CANVAS: Float = 520f

private data class PlacedWord(
    val text: String,
    val size: Float,
    val weight: FontWeight,
    val color: Color,
    val center: Offset,
)

private val Separators: Set<Char> = (
    "的与和到在及对为以其等了是有、，。·？！：；,.?!:;()（）" +
        " \t\n\r"
    ).toSet()

/** Size largest-first by count, then place along an Archimedean spiral with an occupancy grid. */
private fun placeWords(rawCounts: List<Pair<String, Int>>): List<PlacedWord> {
    val words = rawCounts.sortedByDescending { it.second }.take(50)
    if (words.isEmpty()) return emptyList()

    val maxCount = words.first().second
    val minCount = words.last().second
    val span = (maxCount - minCount).coerceAtLeast(1).toDouble()

    data class Sized(val text: String, val size: Float, val weight: FontWeight, val color: Color)
    val sized = words.mapIndexed { index, (text, count) ->
        val norm = (count - minCount) / span
        val px = (14 + norm * 40).roundToInt().toFloat()
        val weight = when {
            norm > 0.6 -> FontWeight.Bold
            norm > 0.3 -> FontWeight.SemiBold
            else -> FontWeight.Medium
        }
        Sized(text, px, weight, WordCloudPalette[index % WordCloudPalette.size])
    }

    // 2) Archimedean-spiral placement with an occupancy grid.
    val cell = 4f
    val cols = (CANVAS / cell).toInt() + 1
    val rows = cols
    val occupied = BooleanArray(cols * rows)
    val mid = CANVAS / 2f
    val pad = 3f
    val out = mutableListOf<PlacedWord>()

    for (item in sized) {
        val w = (estimateWidth(item.text, item.size) + pad * 2).coerceAtLeast(1f)
        val h = (item.size * 1.18f + pad * 2).coerceAtLeast(1f)
        for (step in 0 until 5000) {
            val t = step * 0.22
            val r = 2.5 * t
            val x = (mid + (r * cos(t)).toFloat() - w / 2f).toInt().toFloat()
            val y = (mid + (r * sin(t)).toFloat() - h / 2f).toInt().toFloat()
            if (x < 0 || y < 0 || x + w > CANVAS || y + h > CANVAS) continue
            val c0 = (x / cell).toInt()
            val r0 = (y / cell).toInt()
            val c1 = ((x + w) / cell).toInt() + 1
            val r1 = ((y + h) / cell).toInt() + 1
            var clash = false
            outer@ for (ri in r0 until r1) {
                if (ri !in 0 until rows) continue
                for (ci in c0 until c1) {
                    if (ci !in 0 until cols) continue
                    if (occupied[ri * cols + ci]) { clash = true; break@outer }
                }
            }
            if (clash) continue
            for (ri in r0 until r1) {
                if (ri !in 0 until rows) continue
                for (ci in c0 until c1) {
                    if (ci !in 0 until cols) continue
                    occupied[ri * cols + ci] = true
                }
            }
            out.add(
                PlacedWord(
                    text = item.text,
                    size = item.size,
                    weight = item.weight,
                    color = item.color,
                    center = Offset(x + w / 2f, y + h / 2f),
                )
            )
            break
        }
    }
    return out
}

private fun estimateWidth(text: String, size: Float): Float {
    var acc = 0f
    for (c in text) acc += if (c.code < 128) 0.58f else 1f
    return acc * size
}
