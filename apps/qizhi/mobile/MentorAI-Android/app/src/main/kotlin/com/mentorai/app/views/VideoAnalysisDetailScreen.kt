package com.mentorai.app.views

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountTree
import androidx.compose.material.icons.filled.AutoFixHigh
import androidx.compose.material.icons.filled.BarChart
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Flag
import androidx.compose.material.icons.filled.FormatQuote
import androidx.compose.material.icons.filled.Forum
import androidx.compose.material.icons.filled.HourglassBottom
import androidx.compose.material.icons.filled.Lightbulb
import androidx.compose.material.icons.filled.ListAlt
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.PieChart
import androidx.compose.material.icons.filled.PlayCircleOutline
import androidx.compose.material.icons.filled.RadioButtonUnchecked
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material.icons.filled.ShowChart
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material.icons.filled.Spellcheck
import androidx.compose.material.icons.filled.Tag
import androidx.compose.material.icons.filled.Timeline
import androidx.compose.material.icons.filled.VolumeUp
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshContainer
import androidx.compose.material3.pulltorefresh.rememberPullToRefreshState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.mentorai.app.MentorAIApp
import com.mentorai.app.R
import com.mentorai.app.app.AppState
import com.mentorai.app.ui.VideoPlayerView
import com.mentorai.app.ui.charts.DonutChartView
import com.mentorai.app.ui.charts.FillerWords
import com.mentorai.app.ui.charts.IdeologyEventCard
import com.mentorai.app.ui.charts.InteractionTimeline
import com.mentorai.app.ui.charts.KnowledgeTree
import com.mentorai.app.ui.charts.MetricLineChart
import com.mentorai.app.ui.charts.PhaseAnalysisCard
import com.mentorai.app.ui.charts.RadarChartView
import com.mentorai.app.ui.charts.ScoreBadge
import com.mentorai.app.ui.charts.TeachTimelineView
import com.mentorai.app.ui.charts.WordCloudView
import com.mentorai.app.ui.charts.reportClock
import com.mentorai.app.videoanalysis.AnalysisMode
import com.mentorai.app.videoanalysis.TeachSegment
import com.mentorai.app.videoanalysis.TeachSummarySection
import com.mentorai.app.videoanalysis.VideoAnalysisResult
import com.mentorai.app.videoanalysis.VideoDetail
import com.mentorai.app.videoanalysis.VideoStatus
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Full-screen sub-routes opened from the report (knowledge tree / interaction timeline / segments). */
private sealed class DetailRoute {
    object KnowledgeTree : DetailRoute()
    object Interaction : DetailRoute()
    object TeachSummary : DetailRoute()
}

/** The 总览 + 5 dimension tabs the report is split across. Mirrors iOS `ReportTab`. */
private enum class ReportTab(val title: String) {
    Overview("总览"),
    Expression("教学表达"),
    Design("教学设计"),
    Knowledge("知识呈现"),
    Interaction("互动质量"),
    Ideology("思政融合"),
}

/**
 * V2 five-dimension report rendered as 总览 + 5 dimension tabs with a sticky segmented bar.
 * Mirrors iOS `VideoAnalysisDetailView`.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VideoAnalysisDetailScreen(
    appState: AppState,
    app: MentorAIApp,
    videoId: String,
    previewName: String,
    onDeleted: (String) -> Unit,
    onChanged: () -> Unit,
    onClose: () -> Unit,
) {
    val tokenProvider = { (appState.phase.value as? AppState.Phase.SignedIn)?.session?.accessToken }
    val scope = rememberCoroutineScope()

    var detail by remember { mutableStateOf<VideoDetail?>(null) }
    var isLoading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var analyzeError by remember { mutableStateOf<String?>(null) }
    var pendingDelete by remember { mutableStateOf(false) }
    var analysisMethodPrompt by remember { mutableStateOf(false) }
    var menuOpen by remember { mutableStateOf(false) }
    var route by remember { mutableStateOf<DetailRoute?>(null) }

    suspend fun load(silent: Boolean) {
        val token = tokenProvider() ?: run { if (!silent) error = "未登录"; return }
        if (!silent) { isLoading = true; error = null }
        try {
            detail = app.videoApi.detail(videoId, token)
        } catch (e: Throwable) {
            if (!silent) error = e.localizedMessage ?: "加载失败"
        } finally {
            if (!silent) isLoading = false
        }
    }

    // 选择分析方式：mirrors iOS `triggerAnalyze(mode:)` — the 开始分析 / 开始-重新分析 entry
    // points open the 选择分析方式 dialog, which routes here with the chosen 云端/本地 mode.
    fun startAnalyze(mode: AnalysisMode) {
        val d = detail ?: return
        scope.launch {
            analyzeError = null
            try {
                tokenProvider()?.let { app.videoApi.analyze(d.id, mode, it) }
                load(silent = false)
                onChanged()
            } catch (t: Throwable) {
                analyzeError = t.localizedMessage ?: "启动分析失败"
            }
        }
    }

    LaunchedEffect(videoId) { load(silent = false) }

    DisposableEffect(detail?.status) {
        var job: Job? = null
        if (detail?.status == VideoStatus.Waiting) {
            job = scope.launch {
                while (detail?.status == VideoStatus.Waiting) {
                    delay(4_000)
                    load(silent = true)
                }
                onChanged()
            }
        }
        onDispose { job?.cancel() }
    }

    val parsed = remember(detail?.analysisResult) {
        VideoAnalysisResult.parse(detail?.analysisResult, com.mentorai.app.networking.APIClient.DefaultJson)
    }
    when (route) {
        DetailRoute.KnowledgeTree -> {
            KnowledgeTreeFullScreen(nodes = parsed.knowledgeTree, onClose = { route = null })
            return
        }
        DetailRoute.Interaction -> {
            InteractionTimelineFullScreen(events = parsed.interactionEvents, onClose = { route = null })
            return
        }
        DetailRoute.TeachSummary -> {
            TeachSummaryFullScreen(
                sections = listOf(TeachSummarySection(summary = "", segments = parsed.designSegments)),
                onClose = { route = null },
            )
            return
        }
        null -> Unit
    }

    Scaffold(
        topBar = {
            androidx.compose.material3.Surface(
                color = MaterialTheme.colorScheme.surface,
                tonalElevation = 0.dp,
                modifier = Modifier
                    .fillMaxWidth()
                    .windowInsetsPadding(WindowInsets.statusBars),
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(56.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    IconButton(onClick = onClose) {
                        Icon(Icons.Filled.Close, contentDescription = stringResource(R.string.back_label))
                    }
                    Text(
                        text = detail?.name ?: previewName,
                        maxLines = 1,
                        overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.weight(1f),
                    )
                    IconButton(onClick = { menuOpen = true }) {
                        Icon(Icons.Filled.MoreVert, contentDescription = null)
                    }
                    DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                        DropdownMenuItem(
                            text = { Text("刷新") },
                            onClick = { menuOpen = false; scope.launch { load(silent = false) } },
                        )
                        if (detail?.status != VideoStatus.Waiting) {
                            DropdownMenuItem(
                                text = { Text("开始/重新分析") },
                                onClick = {
                                    menuOpen = false
                                    analysisMethodPrompt = true
                                },
                            )
                        }
                        DropdownMenuItem(
                            text = {
                                Text(stringResource(R.string.chat_common_delete), color = MaterialTheme.colorScheme.error)
                            },
                            onClick = { menuOpen = false; pendingDelete = true },
                        )
                    }
                }
            }
        },
    ) { padding ->
        val current = detail
        when {
            current != null -> {
                val refreshState = rememberPullToRefreshState()
                if (refreshState.isRefreshing) {
                    LaunchedEffect(true) {
                        load(silent = true)
                        refreshState.endRefresh()
                    }
                }
                Box(
                    modifier = Modifier
                        .padding(padding)
                        .fillMaxSize()
                        .nestedScroll(refreshState.nestedScrollConnection),
                ) {
                    DetailBody(
                        detail = current,
                        analysis = parsed,
                        analyzeError = analyzeError,
                        onStartAnalyze = { analysisMethodPrompt = true },
                        onOpenKnowledge = { route = DetailRoute.KnowledgeTree },
                        onOpenInteraction = { route = DetailRoute.Interaction },
                        onOpenTeachSummary = { route = DetailRoute.TeachSummary },
                        modifier = Modifier.fillMaxSize(),
                    )
                    PullToRefreshContainer(
                        state = refreshState,
                        modifier = Modifier.align(Alignment.TopCenter),
                    )
                }
            }
            isLoading -> Box(modifier = Modifier.padding(padding).fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            error != null -> Column(
                modifier = Modifier.padding(padding).fillMaxSize().padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center,
            ) {
                Text("加载失败", style = MaterialTheme.typography.titleMedium)
                Spacer(modifier = Modifier.size(8.dp))
                Text(error!!, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(modifier = Modifier.size(16.dp))
                Button(onClick = { scope.launch { load(silent = false) } }) {
                    Text(stringResource(R.string.common_retry), color = Color.White)
                }
            }
        }
    }

    if (pendingDelete) {
        AlertDialog(
            onDismissRequest = { pendingDelete = false },
            confirmButton = {
                TextButton(onClick = { pendingDelete = false; onDeleted(videoId) }) {
                    Text(stringResource(R.string.chat_common_delete), color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { pendingDelete = false }) { Text(stringResource(R.string.common_cancel)) }
            },
            title = { Text(stringResource(R.string.video_delete_title_generic)) },
            text = { Text(stringResource(R.string.video_delete_confirm)) },
        )
    }

    // 选择分析方式：mirrors the iOS confirmationDialog (云端/本地). Opened by the MoreVert
    // "开始/重新分析" item and the StatusBanner "开始分析" button.
    if (analysisMethodPrompt) {
        AlertDialog(
            onDismissRequest = { analysisMethodPrompt = false },
            title = { Text("选择分析方式") },
            text = { Text("云端分析上传至云端处理，需等待平台；本地分析使用本地模型直接分析视频，不依赖第三方平台。") },
            // 取消 sits on the far right (confirmButton); the two analysis options sit to its left.
            confirmButton = {
                TextButton(onClick = { analysisMethodPrompt = false }) {
                    Text(stringResource(R.string.common_cancel))
                }
            },
            dismissButton = {
                Row {
                    TextButton(onClick = {
                        analysisMethodPrompt = false
                        startAnalyze(AnalysisMode.Local)
                    }) { Text("本地分析") }
                    TextButton(onClick = {
                        analysisMethodPrompt = false
                        startAnalyze(AnalysisMode.Cloud)
                    }) { Text("云端分析") }
                }
            },
        )
    }
}

// -------- body --------

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun DetailBody(
    detail: VideoDetail,
    analysis: VideoAnalysisResult,
    analyzeError: String?,
    onStartAnalyze: () -> Unit,
    onOpenKnowledge: () -> Unit,
    onOpenInteraction: () -> Unit,
    onOpenTeachSummary: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var selectedTab by remember { mutableStateOf(ReportTab.Overview) }
    val tabs = remember(analysis) { ReportTab.values().filter { tabHasContent(it, analysis) } }
    val active = if (selectedTab in tabs) selectedTab else tabs.firstOrNull() ?: ReportTab.Overview

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item { Box(Modifier.fillMaxWidth().padding(horizontal = 16.dp)) { Header(detail) } }
        // 原视频 — always rendered; a placeholder stands in when the path can't resolve to a URL.
        item {
            Column(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                GroupTitle("原视频")
                if (detail.path.isNotBlank()) {
                    VideoPlayerView(rawPath = detail.path)
                } else {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(210.dp)
                            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(12.dp)),
                        contentAlignment = Alignment.Center,
                    ) {
                        Column(
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            Icon(
                                Icons.Filled.PlayCircleOutline,
                                contentDescription = null,
                                modifier = Modifier.size(40.dp),
                                tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f),
                            )
                            Text(
                                "视频播放区",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
                if (detail.name.isNotEmpty()) {
                    Text(detail.name, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
        if (analyzeError != null) {
            item { Box(Modifier.padding(horizontal = 16.dp)) { InlineWarning(analyzeError) } }
        }
        item {
            Box(Modifier.padding(horizontal = 16.dp)) {
                StatusBanner(detail.status, hasPartial = analysis.hasContent, onStartAnalyze = onStartAnalyze)
            }
        }

        if (analysis.hasContent) {
            stickyHeader { ReportTabBar(tabs = tabs, active = active, onSelect = { selectedTab = it }) }
            item {
                Column(
                    Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(20.dp),
                ) {
                    TabContent(active, analysis, onOpenKnowledge, onOpenInteraction, onOpenTeachSummary)
                }
            }
        } else if (detail.status == VideoStatus.Success) {
            item { Box(Modifier.padding(horizontal = 16.dp)) { Text("暂无分析数据。", color = MaterialTheme.colorScheme.onSurfaceVariant) } }
        }
    }
}

private fun tabHasContent(tab: ReportTab, r: VideoAnalysisResult): Boolean = when (tab) {
    ReportTab.Overview -> r.radarAxes.isNotEmpty() || r.overallScore != null || !r.aiSummary.isNullOrEmpty() || r.aiSuggestions.isNotEmpty()
    ReportTab.Expression -> r.speechRate != null || r.volume != null || r.fillerWords.isNotEmpty()
    ReportTab.Design -> r.typeDistribution.isNotEmpty() || r.introAnalysis != null || r.conclusionAnalysis != null || r.infoDensity.isNotEmpty() || r.designSegments.isNotEmpty()
    ReportTab.Knowledge -> r.wordCloud.isNotEmpty() || r.knowledgeTree.isNotEmpty()
    ReportTab.Interaction -> r.whSlices.isNotEmpty() || r.typeStatistics.isNotEmpty() || r.interactionEvents.isNotEmpty()
    ReportTab.Ideology -> r.ideologyEvents.isNotEmpty()
}

@Composable
private fun ReportTabBar(tabs: List<ReportTab>, active: ReportTab, onSelect: (ReportTab) -> Unit) {
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.background)) {
        Row(
            modifier = Modifier
                .horizontalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            tabs.forEach { tab ->
                val selected = tab == active
                Text(
                    tab.title,
                    style = MaterialTheme.typography.bodyMedium.copy(
                        fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
                    ),
                    color = if (selected) Color.White else MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier
                        .clip(RoundedCornerShape(50))
                        .background(if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant)
                        .clickable { onSelect(tab) }
                        .padding(horizontal = 14.dp, vertical = 7.dp),
                )
            }
        }
        Box(Modifier.fillMaxWidth().height(0.5.dp).background(MaterialTheme.colorScheme.outlineVariant))
    }
}

@Composable
private fun TabContent(
    tab: ReportTab,
    result: VideoAnalysisResult,
    onOpenKnowledge: () -> Unit,
    onOpenInteraction: () -> Unit,
    onOpenTeachSummary: () -> Unit,
) {
    when (tab) {
        ReportTab.Overview -> OverviewContent(result)
        ReportTab.Expression -> ExpressionContent(result)
        ReportTab.Design -> DesignContent(result, onOpenTeachSummary)
        ReportTab.Knowledge -> KnowledgeContent(result, onOpenKnowledge)
        ReportTab.Interaction -> InteractionContent(result, onOpenInteraction)
        ReportTab.Ideology -> IdeologyContent(result)
    }
}

// -------- tab content --------

@Composable
private fun OverviewContent(result: VideoAnalysisResult) {
    if (result.radarAxes.isNotEmpty()) {
        Section(
            title = "整体评估概览",
            icon = Icons.Filled.ShowChart,
            accessory = { result.overallScore?.let { ScoreBadge(it) } },
        ) {
            RadarChartView(axes = result.radarAxes)
        }
    }
    val summary = result.aiSummary
    if (!summary.isNullOrEmpty()) {
        Section(title = "AI 总评摘要", icon = Icons.Filled.FormatQuote) {
            Text(summary, style = MaterialTheme.typography.bodySmall)
        }
    }
    if (result.aiSuggestions.isNotEmpty()) {
        Section(title = "总体改进建议", icon = Icons.Filled.Lightbulb) {
            SuggestionList(result.aiSuggestions)
        }
    }
}

@Composable
private fun SuggestionList(lines: List<String>) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        lines.forEachIndexed { index, line ->
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    "${index + 1}.",
                    style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.SemiBold),
                    color = MaterialTheme.colorScheme.primary,
                )
                Text(line, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun ExpressionContent(result: VideoAnalysisResult) {
    val speech = result.speechRate
    if (speech != null) {
        Section(title = "语速分析", icon = Icons.Filled.Speed) {
            MetricLineChart(
                title = "语速变化趋势 (CPM)", samples = speech.samples, unit = "CPM",
                totalDuration = speech.totalDuration, statsAvg = speech.avg, statsMax = speech.max, statsMin = speech.min,
            )
        }
    }
    val volume = result.volume
    if (volume != null) {
        Section(title = "音量分析", icon = Icons.Filled.VolumeUp) {
            MetricLineChart(
                title = "音量变化趋势 (dB)", samples = volume.samples, unit = "dB",
                totalDuration = volume.totalDuration, statsAvg = volume.avg, statsMax = volume.max, statsMin = volume.min,
            )
        }
    }
    if (result.fillerWords.isNotEmpty()) {
        Section(title = "语言精炼度", icon = Icons.Filled.Spellcheck) {
            FillerWords(words = result.fillerWords, ratio = result.fillerRatio, count = result.fillerCount)
        }
    }
}

@Composable
private fun DesignContent(result: VideoAnalysisResult, onOpenTeachSummary: () -> Unit) {
    if (result.typeDistribution.isNotEmpty()) {
        Section(title = "课堂环节占比", icon = Icons.Filled.PieChart) { DonutChartView(slices = result.typeDistribution) }
    }
    val intro = result.introAnalysis
    val conclusion = result.conclusionAnalysis
    if (intro != null || conclusion != null) {
        Section(title = "导入与总结环节分析", icon = Icons.Filled.Flag) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (intro != null) PhaseAnalysisCard("导入环节", intro)
                if (conclusion != null) PhaseAnalysisCard("总结环节", conclusion)
            }
        }
    }
    if (result.infoDensity.isNotEmpty()) {
        Section(title = "信息密度曲线", icon = Icons.Filled.Timeline) {
            MetricLineChart(title = "信息密度", samples = result.infoDensity, fractionDigits = 2)
        }
    }
    if (result.designSegments.isNotEmpty()) {
        Section(title = "教学环节总结", icon = Icons.Filled.ListAlt) {
            DesignSegmentsPreview(result.designSegments, onOpenTeachSummary)
        }
    }
}

@Composable
private fun DesignSegmentsPreview(segments: List<TeachSegment>, onOpenFull: () -> Unit) {
    val preview = segments.take(3)
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        TeachTimelineView(
            sections = listOf(TeachSummarySection(summary = "", segments = preview)),
            contentMaxLines = 2,
        )
        if (segments.size > preview.size) {
            ExpandLabel("查看完整教学环节（共 ${segments.size} 个）", onClick = onOpenFull)
        }
    }
}

@Composable
private fun KnowledgeContent(result: VideoAnalysisResult, onOpenKnowledge: () -> Unit) {
    if (result.knowledgeTree.isNotEmpty()) {
        Section(title = "知识点分布", icon = Icons.Filled.AccountTree) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                KnowledgeTree(nodes = result.knowledgeTree.take(5), maxDepth = 0)
                ExpandLabel("查看完整知识点分布（共 ${result.knowledgeTree.size} 个主题）", onClick = onOpenKnowledge)
            }
        }
    }
    if (result.wordCloud.isNotEmpty()) {
        Section(title = "高频关键词", icon = Icons.Filled.Tag) {
            WordCloudView(words = result.wordCloud.map { it.word to it.weight })
        }
    }
}

@Composable
private fun InteractionContent(result: VideoAnalysisResult, onOpenInteraction: () -> Unit) {
    if (result.whSlices.isNotEmpty()) {
        Section(title = "五何分布", icon = Icons.Filled.Forum) { DonutChartView(slices = result.whSlices) }
    }
    if (result.typeStatistics.isNotEmpty()) {
        Section(title = "互动类型统计", icon = Icons.Filled.BarChart) { DonutChartView(slices = result.typeStatistics) }
    }
    if (result.interactionEvents.isNotEmpty()) {
        Section(title = "互动事件时间轴", icon = Icons.Filled.Schedule) {
            val preview = result.interactionEvents.take(3)
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                InteractionTimeline(events = preview)
                if (result.interactionEvents.size > preview.size) {
                    ExpandLabel("查看完整互动事件时间轴（共 ${result.interactionEvents.size} 条）", onClick = onOpenInteraction)
                }
            }
        }
    }
}

@Composable
private fun IdeologyContent(result: VideoAnalysisResult) {
    Section(title = "思政事件", icon = Icons.Filled.Favorite) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            result.ideologyEvents.forEach { IdeologyEventCard(it) }
        }
    }
}

// -------- shared pieces --------

@Composable
private fun Header(detail: VideoDetail) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatusCapsule(detail.status)
            val analysis = remember(detail.analysisResult) {
                VideoAnalysisResult.parse(detail.analysisResult, com.mentorai.app.networking.APIClient.DefaultJson)
            }
            val duration = analysis.audioDuration
            if (duration != null && duration > 0) {
                Text(
                    "视频时长：${reportClock(duration)}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        if (detail.path.isNotEmpty()) {
            Text(
                detail.path,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
                maxLines = 1,
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            if (detail.createTime.isNotEmpty()) {
                Text(
                    "创建于 ${detail.createTime}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
                )
            }
            val start = detail.analysisStartTime
            if (!start.isNullOrEmpty()) {
                Text(
                    "开始分析 $start",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
                )
            }
        }
    }
}

/** Status icon + label wrapped in a tinted rounded capsule (mirrors iOS header). */
@Composable
private fun StatusCapsule(status: VideoStatus) {
    val (icon, color, label) = when (status) {
        VideoStatus.Unstarted -> Triple(Icons.Filled.RadioButtonUnchecked, MaterialTheme.colorScheme.onSurfaceVariant, R.string.video_status_unstarted)
        VideoStatus.Waiting -> Triple(Icons.Filled.HourglassBottom, Color(0xFFE08E0B), R.string.video_status_waiting)
        VideoStatus.Success -> Triple(Icons.Filled.CheckCircle, Color(0xFF34A853), R.string.video_status_success)
        VideoStatus.Failed -> Triple(Icons.Filled.Warning, MaterialTheme.colorScheme.error, R.string.video_status_failed)
    }
    val fillAlpha = if (status == VideoStatus.Unstarted) 0.15f else 0.18f
    Row(
        modifier = Modifier
            .background(color.copy(alpha = fillAlpha), RoundedCornerShape(50))
            .padding(horizontal = 10.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Icon(icon, contentDescription = null, tint = color, modifier = Modifier.size(14.dp))
        Text(stringResource(label), style = MaterialTheme.typography.labelMedium, color = color)
    }
}

@Composable
private fun StatusBanner(status: VideoStatus, hasPartial: Boolean, onStartAnalyze: () -> Unit) {
    when (status) {
        VideoStatus.Waiting -> Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(10.dp))
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp)
            Text(
                if (hasPartial) "分析中，已生成部分结果，将持续更新…" else "分析中，请稍后…",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        VideoStatus.Failed -> InlineWarning(
            if (hasPartial) "分析未全部完成，以下为已生成的部分结果，可在右上角菜单中重新尝试分析。"
            else "分析失败，可在右上角菜单中重新尝试分析。"
        )
        VideoStatus.Unstarted -> Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("该视频尚未分析。")
            Button(onClick = onStartAnalyze) {
                Icon(
                    Icons.Filled.AutoFixHigh,
                    contentDescription = null,
                    modifier = Modifier.size(18.dp),
                    tint = Color.White,
                )
                Spacer(Modifier.size(8.dp))
                Text("开始分析", color = Color.White)
            }
        }
        else -> Unit
    }
}

@Composable
private fun InlineWarning(text: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.error.copy(alpha = 0.08f), RoundedCornerShape(10.dp))
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(Icons.Filled.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.error)
        Text(text, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
    }
}

@Composable
private fun GroupTitle(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun Section(
    title: String,
    icon: ImageVector,
    accessory: (@Composable () -> Unit)? = null,
    content: @Composable () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(12.dp))
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(16.dp))
            Text(
                title,
                style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold),
                color = MaterialTheme.colorScheme.primary,
            )
            if (accessory != null) {
                Spacer(Modifier.weight(1f))
                accessory()
            }
        }
        content()
    }
}

@Composable
private fun ExpandLabel(text: String, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() }
            .padding(top = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(
            text,
            style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.Medium),
            color = MaterialTheme.colorScheme.primary,
        )
        Icon(
            Icons.Filled.ChevronRight,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier.size(14.dp),
        )
    }
}
