package com.mentorai.app.ui.charts

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.mentorai.app.videoanalysis.FillerWord
import com.mentorai.app.videoanalysis.IdeologyEvent
import com.mentorai.app.videoanalysis.InteractionEvent
import com.mentorai.app.videoanalysis.KnowledgeNode
import com.mentorai.app.videoanalysis.PhaseAnalysis

/** 综合评分 badge shown in the 整体评估概览 header. */
@Composable
fun ScoreBadge(score: Int) {
    Text(
        "综合评分 $score/100",
        style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.SemiBold),
        color = ReportPalette.Primary,
        modifier = Modifier
            .background(ReportPalette.Primary.copy(alpha = 0.12f), RoundedCornerShape(50))
            .padding(horizontal = 8.dp, vertical = 3.dp),
    )
}

/** Small colored score capsule ("87分") used by the analysis cards. */
@Composable
fun ScorePill(score: Int) {
    val c = ReportPalette.scoreColor(score)
    Text(
        "${score}分",
        style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.SemiBold),
        color = c,
        modifier = Modifier
            .background(c.copy(alpha = 0.14f), RoundedCornerShape(50))
            .padding(horizontal = 8.dp, vertical = 3.dp),
    )
}

/** 语言精炼度 — meta line, filler bar chart, and top filler words with examples. */
@Composable
fun FillerWords(words: List<FillerWord>, ratio: Double?, count: Int?, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        val meta = buildList {
            if (ratio != null) add("冗余填充词占比 %.1f%%".format(ratio * 100))
            if (count != null) add("共 $count 次")
        }.joinToString(" · ")
        if (meta.isNotEmpty()) {
            Text(meta, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (words.isNotEmpty()) {
            HorizontalBarChart(items = words.take(8).map { it.term to it.count })
        }
        words.take(5).forEach { word ->
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(word.term, style = MaterialTheme.typography.titleSmall, color = ReportPalette.Primary)
                    Text("×${word.count}", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                word.examples.take(2).forEach { ex ->
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(
                            reportClock(ex.time),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.width(44.dp),
                        )
                        Text(
                            highlight(ex.text, word.term),
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
            }
        }
    }
}

/** 导入/总结环节分析 card — score pill + description + evaluation. */
@Composable
fun PhaseAnalysisCard(title: String, analysis: PhaseAnalysis) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f), RoundedCornerShape(10.dp))
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.titleSmall)
            if (analysis.timeRange.isNotEmpty()) {
                Text(analysis.timeRange, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Spacer(Modifier.weight(1f))
            ScorePill(analysis.score)
        }
        if (analysis.description.isNotEmpty()) Text(analysis.description, style = MaterialTheme.typography.bodySmall)
        if (analysis.evaluation.isNotEmpty()) {
            Text(analysis.evaluation, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

/** 互动事件时间轴 — chronological interaction events with their cognitive type. */
@Composable
fun InteractionTimeline(events: List<InteractionEvent>, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        events.forEach { ev ->
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(reportClock(ev.time), style = MaterialTheme.typography.labelSmall, color = ReportPalette.Primary, modifier = Modifier.width(48.dp))
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    if (ev.type.isNotEmpty()) {
                        val tc = ReportPalette.interactionTypeColor(ev.type)
                        Text(
                            ev.type,
                            style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Medium),
                            color = tc,
                            modifier = Modifier
                                .background(tc.copy(alpha = 0.15f), RoundedCornerShape(50))
                                .padding(horizontal = 6.dp, vertical = 2.dp),
                        )
                    }
                    Text(ev.text, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

/** 思政事件 card. */
@Composable
fun IdeologyEventCard(event: IdeologyEvent) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f), RoundedCornerShape(10.dp))
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(event.title, style = MaterialTheme.typography.titleSmall, color = ReportPalette.Primary, modifier = Modifier.weight(1f))
            if (event.timeRange.isNotEmpty()) {
                Text(event.timeRange, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            ScorePill(event.score)
        }
        if (event.content.isNotEmpty()) Text(event.content, style = MaterialTheme.typography.bodySmall)
        if (event.evaluation.isNotEmpty()) {
            Text(event.evaluation, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

/** 知识点分布 — nested knowledge tree as an indented outline. `maxDepth` limits levels (null = all). */
@Composable
fun KnowledgeTree(nodes: List<KnowledgeNode>, maxDepth: Int? = null, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        nodes.forEach { KnowledgeNodeRow(it, 0, maxDepth) }
    }
}

@Composable
private fun KnowledgeNodeRow(node: KnowledgeNode, depth: Int, maxDepth: Int?) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Box(
                modifier = Modifier
                    .size(if (depth == 0) 7.dp else 5.dp)
                    .background(if (depth == 0) ReportPalette.Primary else Color.Gray.copy(alpha = 0.4f), CircleShape),
            )
            Text(
                node.title,
                style = if (depth == 0) MaterialTheme.typography.titleSmall else MaterialTheme.typography.bodySmall,
                color = if (depth == 0) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.weight(1f),
            )
            if (node.timeRange.isNotEmpty()) {
                Text(node.timeRange, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        if (node.children.isNotEmpty() && (maxDepth == null || depth < maxDepth)) {
            Column(modifier = Modifier.padding(start = 14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                node.children.forEach { KnowledgeNodeRow(it, depth + 1, maxDepth) }
            }
        }
    }
}
