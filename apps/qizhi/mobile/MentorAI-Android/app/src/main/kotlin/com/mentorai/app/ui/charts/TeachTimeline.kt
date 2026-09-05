package com.mentorai.app.ui.charts

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.mentorai.app.videoanalysis.TeachSegment
import com.mentorai.app.videoanalysis.TeachSummarySection

/**
 * 教学环节总结 — vertical timeline of structured teaching segments. Mirrors iOS
 * `TeachTimelineView`. Supports optional `highlight` query to bold/yellow-highlight matches
 * (e.g. when used inside `TeachSummaryFullScreen`'s search).
 */
@Composable
fun TeachTimelineView(
    sections: List<TeachSummarySection>,
    contentMaxLines: Int = Int.MAX_VALUE,
    highlight: String = "",
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(16.dp)) {
        for (section in sections) {
            if (section.summary.isNotEmpty()) {
                Text(
                    highlight(section.summary, highlight),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            section.segments.forEachIndexed { index, segment ->
                TimelineRow(
                    segment = segment,
                    isLast = index == section.segments.size - 1,
                    contentMaxLines = contentMaxLines,
                    highlight = highlight,
                )
            }
        }
    }
}

@Composable
private fun TimelineRow(
    segment: TeachSegment,
    isLast: Boolean,
    contentMaxLines: Int,
    highlight: String,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(IntrinsicSize.Min),
        verticalAlignment = Alignment.Top,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.width(10.dp)) {
            Box(
                modifier = Modifier
                    .padding(top = 5.dp)
                    .size(8.dp)
                    .background(ReportPalette.Primary, CircleShape),
            )
            if (!isLast) {
                Box(
                    modifier = Modifier
                        .padding(top = 2.dp)
                        .width(1.5.dp)
                        .fillMaxHeight()
                        .background(Color.Gray.copy(alpha = 0.25f)),
                )
            }
        }
        Column(
            modifier = Modifier.weight(1f).padding(bottom = if (isLast) 0.dp else 4.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(
                    highlight(segment.type, highlight),
                    style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.SemiBold),
                    color = ReportPalette.Primary,
                )
                if (segment.startTime.isNotEmpty()) {
                    Text(
                        "${segment.startTime} - ${segment.endTime}",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
                    )
                }
            }
            if (segment.content.isNotEmpty()) {
                Text(
                    highlight(segment.content, highlight),
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = contentMaxLines,
                )
            }
            if (segment.keypoint.isNotEmpty()) {
                Row(
                    verticalAlignment = Alignment.Top,
                    horizontalArrangement = Arrangement.spacedBy(2.dp),
                ) {
                    Text(
                        "关键点：",
                        style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.SemiBold),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Text(
                        highlight(segment.keypoint, highlight),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

/** Returns `text` with every case-insensitive occurrence of `query` highlighted. */
internal fun highlight(text: String, query: String): AnnotatedString {
    val trimmed = query.trim()
    if (trimmed.isEmpty()) return AnnotatedString(text)
    return buildAnnotatedString {
        append(text)
        var start = 0
        while (true) {
            val found = text.indexOf(trimmed, startIndex = start, ignoreCase = true)
            if (found < 0) break
            addStyle(
                SpanStyle(background = Color(0xFFFFF59D), color = Color(0xFF111111)),
                found, found + trimmed.length,
            )
            start = found + trimmed.length
        }
    }
}
