package com.mentorai.app.views

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.HourglassBottom
import androidx.compose.material.icons.filled.PlayCircle
import androidx.compose.material.icons.filled.RadioButtonUnchecked
import androidx.compose.material.icons.filled.VideoFile
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.mentorai.app.MentorAIApp
import com.mentorai.app.R
import com.mentorai.app.app.AppState
import com.mentorai.app.support.ServerDate
import com.mentorai.app.videoanalysis.VideoListViewModel
import com.mentorai.app.videoanalysis.VideoStatus
import com.mentorai.app.videoanalysis.VideoSummary
import kotlinx.coroutines.delay
import java.util.UUID
import kotlin.math.ceil

private val DateRegex = Regex("\\s*\\d{4}-\\d{2}-\\d{2}.*$")

/**
 * 资源分析 list — mirrors iOS `VideoAnalysisListView`. Groups by course (derived from the
 * date pattern in the video name) and falls back to 本地视频 when no date is present.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VideoAnalysisListScreen(appState: AppState, app: MentorAIApp) {
    val vm = remember {
        VideoListViewModel(
            api = app.videoApi,
            tokenProvider = { (appState.phase.value as? AppState.Phase.SignedIn)?.session?.accessToken },
        )
    }
    val context = LocalContext.current
    val videos by vm.videos.collectAsState()
    val isLoading by vm.isLoading.collectAsState()
    val error by vm.error.collectAsState()
    val videoTasks by vm.videoTasks.collectAsState()

    var route: VideoRoute? by rememberSaveable(stateSaver = VideoRouteSaver) { mutableStateOf(null) }
    var pendingDelete by remember { mutableStateOf<VideoSummary?>(null) }

    // Auto-refresh: while any video is 分析中 (WAITING), re-fetch every 4s so its status flips to
    // 已完成 / 分析失败 (and the count re-syncs) without a manual pull. Idles once nothing is
    // analyzing. Mirrors iOS VideoAnalysisListView `.task` loop.
    LaunchedEffect(Unit) {
        vm.refresh()
        while (true) {
            delay(4_000)
            if (vm.hasAnalyzingVideos.value) {
                vm.refresh(silent = true)
            }
        }
    }

    when (val r = route) {
        is VideoRoute.New -> {
            NewVideoAnalysisScreen(
                appState = appState,
                app = app,
                // Both add-video flows hand off to the (persistent) list VM, which runs them so
                // they survive this screen closing; progress then shows in the bottom task banner.
                onZhiyunImport = { course, importId ->
                    vm.startZhiyunImport(course, importId)
                    route = null
                },
                onUpload = { uri, name ->
                    vm.startLocalUpload(context, uri, name)
                    route = null
                },
                onClose = { route = null },
            )
            return
        }
        is VideoRoute.Detail -> {
            VideoAnalysisDetailScreen(
                appState = appState,
                app = app,
                videoId = r.id,
                previewName = r.name,
                onDeleted = { id ->
                    vm.delete(id)
                    route = null
                },
                onChanged = { vm.refresh() },
                onClose = { route = null },
            )
            return
        }
        null -> Unit
    }

    Scaffold(
        // Inside MainScreen's Scaffold (which already reserves the bottom nav bar); zero this inner
        // Scaffold's window insets so it doesn't add a second bottom inset — that double inset is
        // the gap between the page and the tab bar. The TopAppBar still handles the status bar.
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        topBar = {
            CenterAlignedTopAppBar(title = { Text(stringResource(R.string.tab_resource_analysis)) })
        },
        floatingActionButton = {
            FloatingActionButton(onClick = { route = VideoRoute.New }) {
                Icon(Icons.Filled.Add, contentDescription = null)
            }
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize(),
        ) {
            Box(modifier = Modifier.weight(1f).fillMaxWidth()) {
                when {
                    error != null && videos.isEmpty() -> ListErrorState(error!!) { vm.refresh() }
                    videos.isEmpty() && !isLoading -> ListEmptyState()
                    else -> GroupedVideoList(
                        videos = videos,
                        onOpen = { v -> route = VideoRoute.Detail(v.id, v.name) },
                        onRequestDelete = { pendingDelete = it },
                    )
                }
            }
            // Pinned at the bottom: in-flight add-video tasks run on the list VM so they keep going
            // after the add screen closes; progress shows here. Mirrors iOS
            // `.safeAreaInset(edge: .bottom) { taskBanner }`.
            TaskBanner(
                tasks = videoTasks,
                onCancel = { vm.cancelVideoTask(it) },
                onDismiss = { vm.dismissTaskBanner(it) },
            )
        }
    }

    pendingDelete?.let { v ->
        AlertDialog(
            onDismissRequest = { pendingDelete = null },
            confirmButton = {
                TextButton(onClick = {
                    val id = v.id
                    pendingDelete = null
                    vm.delete(id)
                }) {
                    Text(stringResource(R.string.chat_common_delete), color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { pendingDelete = null }) { Text(stringResource(R.string.common_cancel)) }
            },
            title = {
                Text(
                    if (v.name.isNotBlank()) stringResource(R.string.video_delete_title_named, v.name)
                    else stringResource(R.string.video_delete_title_generic),
                )
            },
            text = { Text(stringResource(R.string.video_delete_confirm)) },
        )
    }
}

sealed class VideoRoute {
    object New : VideoRoute()
    data class Detail(val id: String, val name: String) : VideoRoute()
}

private val VideoRouteSaver = androidx.compose.runtime.saveable.Saver<VideoRoute?, String>(
    save = { route ->
        when (route) {
            null -> ""
            VideoRoute.New -> "new"
            is VideoRoute.Detail -> "detail:${route.id}|${route.name}"
        }
    },
    restore = { token ->
        when {
            token.isEmpty() -> null
            token == "new" -> VideoRoute.New
            token.startsWith("detail:") -> {
                val rest = token.removePrefix("detail:")
                val pipe = rest.indexOf('|')
                if (pipe >= 0) VideoRoute.Detail(rest.substring(0, pipe), rest.substring(pipe + 1))
                else VideoRoute.Detail(rest, rest)
            }
            else -> null
        }
    },
)

private data class VideoGroup(val name: String, val videos: List<VideoSummary>)

@Composable
private fun GroupedVideoList(
    videos: List<VideoSummary>,
    onOpen: (VideoSummary) -> Unit,
    onRequestDelete: (VideoSummary) -> Unit,
) {
    val grouped = remember(videos) { groupByCourse(videos) }
    LazyColumn(modifier = Modifier.fillMaxSize()) {
        for (group in grouped) {
            item(key = "header:${group.name}") {
                Text(
                    text = "${group.name}（${group.videos.size}）",
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 8.dp),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            items(items = group.videos, key = { it.id.ifEmpty { it.name + it.createTime } }) { video ->
                VideoRow(
                    video = video,
                    title = sessionTitle(video, group.name),
                    onClick = { onOpen(video) },
                    onRequestDelete = { onRequestDelete(video) },
                )
                HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun VideoRow(
    video: VideoSummary,
    title: String,
    onClick: () -> Unit,
    onRequestDelete: () -> Unit,
) {
    val dismissState = rememberSwipeToDismissBoxState(
        confirmValueChange = { value ->
            if (value == SwipeToDismissBoxValue.EndToStart) {
                onRequestDelete()
                false
            } else false
        },
    )
    SwipeToDismissBox(
        state = dismissState,
        enableDismissFromStartToEnd = false,
        backgroundContent = {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(MaterialTheme.colorScheme.error)
                    .padding(horizontal = 24.dp),
                contentAlignment = Alignment.CenterEnd,
            ) {
                Icon(Icons.Filled.Delete, contentDescription = null, tint = Color.White)
            }
        },
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.surface)
                .clickable { onClick() }
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.Top,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Box(
                modifier = Modifier
                    .size(44.dp)
                    .background(
                        MaterialTheme.colorScheme.primary.copy(alpha = 0.12f),
                        RoundedCornerShape(10.dp),
                    ),
                contentAlignment = Alignment.Center,
            ) {
                Icon(Icons.Filled.PlayCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            }
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Text(
                    title,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Medium,
                    maxLines = 2,
                )
                StatusRow(status = video.status, eta = etaText(video))
                Text(
                    ServerDate.relative(video.createTime),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
                )
            }
        }
    }
}

@Composable
fun StatusRow(status: VideoStatus, eta: String? = null) {
    val (icon, color, label) = when (status) {
        VideoStatus.Unstarted -> Triple(Icons.Filled.RadioButtonUnchecked, MaterialTheme.colorScheme.onSurfaceVariant, R.string.video_status_unstarted)
        VideoStatus.Waiting -> Triple(Icons.Filled.HourglassBottom, Color(0xFFE08E0B), R.string.video_status_waiting)
        VideoStatus.Success -> Triple(Icons.Filled.CheckCircle, Color(0xFF34A853), R.string.video_status_success)
        VideoStatus.Failed -> Triple(Icons.Filled.Warning, MaterialTheme.colorScheme.error, R.string.video_status_failed)
    }
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Icon(icon, contentDescription = null, tint = color, modifier = Modifier.size(14.dp))
        Text(stringResource(label), style = MaterialTheme.typography.labelMedium, color = color)
        if (eta != null) {
            Text(
                "· $eta",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * 本地分析「分析中」的预计剩余时间（用后端 estimated_seconds，含排队+并发+时长；列表每 4s 自动
 * 刷新带回最新值）。云端分析为 null → 不显示。Mirrors iOS `VideoRow.etaText`.
 */
@Composable
private fun etaText(video: VideoSummary): String? {
    if (video.status != VideoStatus.Waiting) return null
    val secs = video.estimatedSeconds ?: return null
    if (secs <= 0) return null
    if (secs <= 30) return stringResource(R.string.video_eta_imminent)
    val totalMin = maxOf(1, ceil(secs / 60.0).toInt())
    val h = totalMin / 60
    val m = totalMin % 60
    return when {
        h > 0 && m > 0 -> stringResource(R.string.video_eta_remaining_h_m, h, m)
        h > 0 -> stringResource(R.string.video_eta_remaining_h, h)
        else -> stringResource(R.string.video_eta_remaining_m, m)
    }
}

// -------- in-flight add-video task banner (mirrors iOS taskBanner / taskRow) --------

/**
 * In-flight add-video tasks (智云 import / 本地 upload), one row each, pinned above the list. The
 * tasks run on the (persistent) list ViewModel, so they keep going after the add-video screen
 * closes. Renders nothing (zero height) when nothing is in flight.
 */
@Composable
private fun TaskBanner(
    tasks: List<VideoListViewModel.VideoTaskState>,
    onCancel: (UUID) -> Unit,
    onDismiss: (UUID) -> Unit,
) {
    if (tasks.isEmpty()) return
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface),
    ) {
        for (task in tasks) {
            HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
            TaskRow(task = task, onCancel = onCancel, onDismiss = onDismiss)
        }
    }
}

@Composable
private fun TaskRow(
    task: VideoListViewModel.VideoTaskState,
    onCancel: (UUID) -> Unit,
    onDismiss: (UUID) -> Unit,
) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 10.dp),
    ) {
        when (val phase = task.phase) {
            VideoListViewModel.VideoTaskState.Phase.Running -> {
                val detailSuffix = if (task.detail.isEmpty()) "" else " · ${task.detail}"
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                    Column(
                        modifier = Modifier.weight(1f),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        Text(
                            stringResource(R.string.video_task_running_label, task.verb, task.title, detailSuffix),
                            style = MaterialTheme.typography.labelMedium,
                            maxLines = 1,
                        )
                        val percent = task.percent
                        if (percent != null) {
                            LinearProgressIndicator(
                                progress = { percent / 100f },
                                modifier = Modifier.fillMaxWidth(),
                            )
                        } else {
                            LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                        }
                    }
                    task.percent?.let { percent ->
                        Text(
                            "$percent%",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    TextButton(onClick = { onCancel(task.id) }) {
                        Text(stringResource(R.string.common_cancel), color = MaterialTheme.colorScheme.error)
                    }
                }
            }
            VideoListViewModel.VideoTaskState.Phase.Done -> {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Icon(Icons.Filled.CheckCircle, contentDescription = null, tint = Color(0xFF34A853))
                    Text(
                        stringResource(R.string.video_task_done_label, task.title, task.verb),
                        style = MaterialTheme.typography.labelMedium,
                        maxLines = 1,
                    )
                }
            }
            is VideoListViewModel.VideoTaskState.Phase.Failed -> {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Icon(Icons.Filled.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.error)
                    Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(
                            stringResource(R.string.video_task_failed_label, task.title, task.verb),
                            style = MaterialTheme.typography.labelMedium,
                        )
                        Text(
                            phase.message,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 2,
                        )
                    }
                    TextButton(onClick = { onDismiss(task.id) }) {
                        Text(stringResource(R.string.video_task_close))
                    }
                }
            }
        }
    }
}

@Composable
private fun ListEmptyState() {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(
            Icons.Filled.VideoFile,
            contentDescription = null,
            modifier = Modifier.size(56.dp),
            tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f),
        )
        Spacer(modifier = Modifier.size(16.dp))
        Text(stringResource(R.string.video_empty_title), style = MaterialTheme.typography.titleMedium)
        Spacer(modifier = Modifier.size(8.dp))
        Text(
            stringResource(R.string.video_empty_subtitle),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun ListErrorState(message: String, onRetry: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(
            Icons.Filled.Warning,
            contentDescription = null,
            modifier = Modifier.size(44.dp),
            tint = MaterialTheme.colorScheme.error,
        )
        Spacer(modifier = Modifier.size(12.dp))
        Text(stringResource(R.string.video_list_error_title), style = MaterialTheme.typography.titleMedium)
        Spacer(modifier = Modifier.size(8.dp))
        Text(message, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(modifier = Modifier.size(16.dp))
        Button(onClick = onRetry) { Text(stringResource(R.string.common_retry), color = Color.White) }
    }
}

// -------- grouping (matches iOS courseName(from:) + sessionTitle) --------

private fun groupByCourse(videos: List<VideoSummary>): List<VideoGroup> {
    val order = mutableListOf<String>()
    val buckets = linkedMapOf<String, MutableList<VideoSummary>>()
    for (v in videos) {
        val key = courseNameFromVideoName(v.name)
        if (key !in buckets) { buckets[key] = mutableListOf(); order.add(key) }
        buckets[key]!!.add(v)
    }
    return order.map { VideoGroup(it, buckets[it].orEmpty()) }
}

private fun courseNameFromVideoName(name: String): String {
    val match = DateRegex.find(name) ?: return "本地视频"
    val prefix = name.substring(0, match.range.first).trim()
    return prefix.ifEmpty { "本地视频" }
}

private fun sessionTitle(video: VideoSummary, course: String): String {
    val raw = video.name.trim()
    if (raw != course && raw.startsWith(course)) {
        val remainder = raw.removePrefix(course).trim()
        if (remainder.isNotEmpty()) return remainder
    }
    return raw.ifEmpty { "未命名视频" }
}
