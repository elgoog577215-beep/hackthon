package com.mentorai.app.videoanalysis

import android.content.Context
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.mentorai.app.networking.AuthError
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.io.RandomAccessFile
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.UUID

/**
 * Mirrors iOS `VideoListViewModel` — refresh (with a silent auto-poll path), optimistic insert /
 * delete, and ownership of the foreground-continue add-video tasks (智云 import / 本地 upload).
 * The screen groups by course name in its own layout (parallels iOS).
 */
class VideoListViewModel(
    private val api: VideoAPI,
    private val tokenProvider: () -> String?,
) : ViewModel() {

    private val _videos = MutableStateFlow<List<VideoSummary>>(emptyList())
    val videos: StateFlow<List<VideoSummary>> = _videos.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    /**
     * True while any video is still analyzing (WAITING). Drives the list's auto-poll so a 分析中
     * row flips to 已完成 / 分析失败 (and the count re-syncs) without a manual pull.
     */
    val hasAnalyzingVideos: StateFlow<Boolean> = videos
        .map { list -> list.any { it.status == VideoStatus.Waiting } }
        .stateIn(viewModelScope, SharingStarted.Eagerly, false)

    /**
     * `silent` is used by the auto-poll: it won't toggle the loading spinner, surface transient
     * errors, or clear the current list — a failed poll just leaves things as-is. A genuine
     * (non-silent) 401 on /video/list degrades to an empty list (a 暂不登录 / test session has no
     * permission for resource analysis; the server replies 401「无操作权限」, and a "重试" button can
     * never succeed — so we match the web client and show the normal empty state instead).
     */
    fun refresh(silent: Boolean = false) {
        val token = tokenProvider()
        if (token.isNullOrEmpty()) {
            if (!silent) _error.value = "未登录"
            return
        }
        if (!silent) {
            _isLoading.value = true
            _error.value = null
        }
        viewModelScope.launch {
            try {
                val list = api.list(token)
                _videos.value = list.sortedByDescending { it.createTime }
            } catch (err: AuthError) {
                if (!silent) {
                    // OkHttp maps a 401 to AuthError.Unauthorized; the server may also reply
                    // Server(401). Either way, degrade to the empty state.
                    if (err is AuthError.Unauthorized || (err is AuthError.Server && err.status == 401)) {
                        _videos.value = emptyList()
                        _error.value = null
                    } else {
                        _error.value = err.errorDescription
                    }
                }
                // silent: swallow, keep the current list (no flicker).
            } catch (t: Throwable) {
                if (!silent) _error.value = t.localizedMessage ?: "加载失败"
            } finally {
                if (!silent) _isLoading.value = false
            }
        }
    }

    /** Insert (or replace) a summary, then keep the list sorted by createTime DESC. */
    fun insert(summary: VideoSummary) {
        _videos.update { list ->
            (list.filterNot { it.id == summary.id } + summary).sortedByDescending { it.createTime }
        }
    }

    /** Optimistic delete: remove now, roll back (and re-sort) if the server rejects it. */
    fun delete(id: String) {
        val token = tokenProvider()
        if (token.isNullOrEmpty()) return
        val current = _videos.value
        val removed = current.firstOrNull { it.id == id } ?: return
        _videos.value = current.filterNot { it.id == id }
        viewModelScope.launch {
            try {
                api.operate(VideoOperationRequest(operation = VideoOperation.Delete, id = id), token)
            } catch (err: AuthError) {
                _videos.update { (it + removed).sortedByDescending { v -> v.createTime } }
                _error.value = err.errorDescription
            } catch (t: Throwable) {
                _videos.update { (it + removed).sortedByDescending { v -> v.createTime } }
                _error.value = t.localizedMessage ?: "删除失败"
            }
        }
    }

    // MARK: - Add-video tasks (智云 import / 本地 upload) — foreground-continue

    /**
     * One in-flight add-video task (a 智云 import or a local upload), surfaced as a banner on the
     * list. The task is owned HERE — not by the add-video screen — so the user can close that
     * screen (返回) and the work keeps running while the app stays foreground. On success the video
     * is inserted as 未开始分析; there is NO auto-analysis — the user picks 云端 / 本地 on the detail
     * page. Both sources go through this same path, so the two flows are identical.
     */
    data class VideoTaskState(
        val kind: Kind,
        val title: String,
        val detail: String,      // 导入中 / 上传中 / 合并中 / 创建中 …
        val percent: Int?,       // null → indeterminate (spinner, no bar)
        val phase: Phase,
        val id: UUID = UUID.randomUUID(),
    ) {
        enum class Kind { Importing, Uploading }

        sealed class Phase {
            object Running : Phase()
            object Done : Phase()
            data class Failed(val message: String) : Phase()
        }

        val verb: String get() = if (kind == Kind.Importing) "导入" else "上传"
    }

    /**
     * Tasks run concurrently — a 智云 import and any number of local uploads can be in flight at
     * once; each has its own coroutine [Job] and its own row in the banner.
     */
    private val _videoTasks = MutableStateFlow<List<VideoTaskState>>(emptyList())
    val videoTasks: StateFlow<List<VideoTaskState>> = _videoTasks.asStateFlow()

    private val videoTaskHandles = mutableMapOf<UUID, Job>()

    /** taskId → 智云导入的 import_id（仅 import 任务有）；取消时据此通知后端取消导入。 */
    private val zhiyunImportIds = mutableMapOf<UUID, String>()

    fun cancelVideoTask(id: UUID) {
        videoTaskHandles[id]?.cancel()
        // 智云导入：仅取消客户端 Job 不可靠（后端会继续下载并落库，视频随后仍出现在列表里），需显式
        // 通知后端写取消标记。本地上传无此问题（取消即停止分片，最终 create 不会发生）。
        val importId = zhiyunImportIds[id]
        val token = tokenProvider()
        if (!importId.isNullOrEmpty() && !token.isNullOrEmpty()) {
            viewModelScope.launch { runCatching { api.cancelZhiyunImport(importId, token) } }
        }
        removeTask(id)
    }

    /** Dismiss a finished (done/failed) row; a running task is left alone. */
    fun dismissTaskBanner(id: UUID) {
        val task = _videoTasks.value.firstOrNull { it.id == id } ?: return
        if (task.phase is VideoTaskState.Phase.Running) return
        removeTask(id)
    }

    private fun removeTask(id: UUID) {
        _videoTasks.update { list -> list.filterNot { it.id == id } }
        videoTaskHandles.remove(id)
        zhiyunImportIds.remove(id)
    }

    private fun mutateTask(id: UUID, change: (VideoTaskState) -> VideoTaskState) {
        _videoTasks.update { list -> list.map { if (it.id == id) change(it) else it } }
    }

    /** Shared completion: insert the new (unstarted) video, flash 完成, then auto-clear the row. */
    private suspend fun finishVideoTask(taskId: UUID, videoId: String, name: String) {
        insert(
            VideoSummary(
                id = videoId,
                name = name,
                status = VideoStatus.Unstarted,
                createTime = isoNow(),
            )
        )
        mutateTask(taskId) { it.copy(detail = "", percent = 100, phase = VideoTaskState.Phase.Done) }
        refresh(silent = true)
        delay(2_000)
        val task = _videoTasks.value.firstOrNull { it.id == taskId }
        if (task != null && task.phase is VideoTaskState.Phase.Done) {
            removeTask(taskId)
        }
    }

    // MARK: 智云课堂 import

    /**
     * Run a 智云课堂 import owned by this list ViewModel so it survives the add-video screen closing.
     * `importId` is echoed to the backend so [cancelVideoTask] can write an out-of-band cancel
     * marker. Mirrors iOS `startZhiyunImport`.
     */
    fun startZhiyunImport(course: ZhiyunCourse, importId: String = UUID.randomUUID().toString()) {
        val token = tokenProvider()
        // Match the name the server stores ("课程名 + 章节") so the row groups under its course.
        val displayName = listOf(course.courseName.trim(), course.subTitle.trim())
            .filter { it.isNotEmpty() }
            .joinToString(" ")
        if (token.isNullOrEmpty()) {
            _videoTasks.update {
                it + VideoTaskState(
                    kind = VideoTaskState.Kind.Importing,
                    title = course.courseName,
                    detail = "",
                    percent = null,
                    phase = VideoTaskState.Phase.Failed("未登录"),
                )
            }
            return
        }
        val task = VideoTaskState(
            kind = VideoTaskState.Kind.Importing,
            title = displayName,
            detail = "导入中",
            percent = 0,
            phase = VideoTaskState.Phase.Running,
        )
        val taskId = task.id
        zhiyunImportIds[taskId] = importId
        _videoTasks.update { it + task }
        videoTaskHandles[taskId] = viewModelScope.launch {
            try {
                var lastId: String? = null
                var endId: String? = null
                var reachedEnd = false
                var failed = false
                api.importZhiyun(course.courseId, course.subId, importId, token).collect { event ->
                    when (event) {
                        is VideoAPI.ZhiyunImportEvent.Start ->
                            lastId = event.videoId
                        is VideoAPI.ZhiyunImportEvent.Progress ->
                            mutateTask(taskId) { it.copy(percent = event.percent.coerceIn(0, 100)) }
                        is VideoAPI.ZhiyunImportEvent.Error -> {
                            mutateTask(taskId) { it.copy(phase = VideoTaskState.Phase.Failed(event.message)) }
                            failed = true
                        }
                        is VideoAPI.ZhiyunImportEvent.End -> {
                            endId = event.videoId
                            reachedEnd = true
                        }
                    }
                }
                when {
                    failed -> Unit
                    reachedEnd -> {
                        val id = endId ?: lastId
                        if (id.isNullOrEmpty()) {
                            mutateTask(taskId) {
                                it.copy(phase = VideoTaskState.Phase.Failed("导入完成但缺少视频 ID"))
                            }
                        } else {
                            finishVideoTask(taskId, id, displayName)
                        }
                    }
                    else -> mutateTask(taskId) {
                        if (it.phase is VideoTaskState.Phase.Running) {
                            it.copy(phase = VideoTaskState.Phase.Failed("导入提前结束"))
                        } else {
                            it
                        }
                    }
                }
            } catch (cancel: CancellationException) {
                removeTask(taskId)
                throw cancel
            } catch (err: AuthError) {
                mutateTask(taskId) { it.copy(phase = VideoTaskState.Phase.Failed(err.errorDescription ?: "导入失败")) }
            } catch (t: Throwable) {
                mutateTask(taskId) { it.copy(phase = VideoTaskState.Phase.Failed(t.localizedMessage ?: "导入失败")) }
            } finally {
                videoTaskHandles.remove(taskId)
            }
        }
    }

    // MARK: 本地视频 upload (init → 分片上传 → finish → create)

    /**
     * Run a local-file upload owned by this list ViewModel so it survives the add-video screen
     * closing. `name` is the display/record name (also used as the upload filename). A [Context] is
     * required to read the content [Uri] (iOS reads the file URL directly). Mirrors iOS
     * `startLocalUpload`.
     */
    fun startLocalUpload(context: Context, uri: Uri, name: String) {
        val token = tokenProvider()
        val displayName = name.trim().ifEmpty { "未命名视频" }
        if (token.isNullOrEmpty()) {
            _videoTasks.update {
                it + VideoTaskState(
                    kind = VideoTaskState.Kind.Uploading,
                    title = displayName,
                    detail = "",
                    percent = null,
                    phase = VideoTaskState.Phase.Failed("未登录"),
                )
            }
            return
        }
        val task = VideoTaskState(
            kind = VideoTaskState.Kind.Uploading,
            title = displayName,
            detail = "初始化中",
            percent = null,
            phase = VideoTaskState.Phase.Running,
        )
        val taskId = task.id
        val appContext = context.applicationContext
        _videoTasks.update { it + task }
        videoTaskHandles[taskId] = viewModelScope.launch {
            var staged: File? = null
            try {
                val file: File = try {
                    VideoAPI.stageUpload(appContext, uri, name)
                } catch (cancel: CancellationException) {
                    throw cancel
                } catch (t: Throwable) {
                    mutateTask(taskId) {
                        it.copy(phase = VideoTaskState.Phase.Failed("读取视频失败：${t.localizedMessage ?: ""}"))
                    }
                    return@launch
                }
                staged = file
                val chunkSize = VideoAPI.CHUNK_SIZE
                val chunks = (((file.length() + chunkSize - 1) / chunkSize).toInt()).coerceAtLeast(1)

                // init
                val uploadId = try {
                    api.initUpload(chunks, token)
                } catch (cancel: CancellationException) {
                    throw cancel
                } catch (err: AuthError) {
                    mutateTask(taskId) { it.copy(phase = VideoTaskState.Phase.Failed(err.errorDescription ?: "初始化失败")) }
                    return@launch
                } catch (t: Throwable) {
                    mutateTask(taskId) { it.copy(phase = VideoTaskState.Phase.Failed(t.localizedMessage ?: "初始化失败")) }
                    return@launch
                }

                // 分片上传 (sequential)
                mutateTask(taskId) { it.copy(detail = "上传中", percent = 0) }
                try {
                    withContext(Dispatchers.IO) {
                        RandomAccessFile(file, "r").use { raf ->
                            val buffer = ByteArray(chunkSize)
                            for (index in 0 until chunks) {
                                ensureActive()
                                val read = raf.read(buffer)
                                if (read <= 0) break
                                val payload = if (read == buffer.size) buffer else buffer.copyOf(read)
                                api.uploadChunk(uploadId, index, payload, name, token)
                                // Reach 100 on the final chunk (matches iOS).
                                mutateTask(taskId) { it.copy(percent = (index + 1) * 100 / chunks) }
                            }
                        }
                    }
                } catch (cancel: CancellationException) {
                    throw cancel
                } catch (err: AuthError) {
                    mutateTask(taskId) { it.copy(phase = VideoTaskState.Phase.Failed(err.errorDescription ?: "分片上传失败")) }
                    return@launch
                } catch (t: Throwable) {
                    mutateTask(taskId) { it.copy(phase = VideoTaskState.Phase.Failed("分片上传失败：${t.localizedMessage ?: ""}")) }
                    return@launch
                }

                // finish (merge)
                mutateTask(taskId) { it.copy(detail = "合并中", percent = null) }
                val result = try {
                    api.finishUpload(uploadId, token)
                } catch (cancel: CancellationException) {
                    throw cancel
                } catch (err: AuthError) {
                    mutateTask(taskId) { it.copy(phase = VideoTaskState.Phase.Failed(err.errorDescription ?: "合并上传失败")) }
                    return@launch
                } catch (t: Throwable) {
                    mutateTask(taskId) { it.copy(phase = VideoTaskState.Phase.Failed(t.localizedMessage ?: "合并上传失败")) }
                    return@launch
                }

                // create record (UNSTARTED — no auto-analysis); cover is optional (nullable).
                mutateTask(taskId) { it.copy(detail = "创建中") }
                try {
                    val newId = api.operate(
                        VideoOperationRequest(
                            operation = VideoOperation.Create,
                            name = displayName,
                            path = result.videoPath,
                            cover = result.coverPath,
                        ),
                        token,
                    )
                    finishVideoTask(taskId, newId, displayName)
                } catch (cancel: CancellationException) {
                    throw cancel
                } catch (err: AuthError) {
                    mutateTask(taskId) { it.copy(phase = VideoTaskState.Phase.Failed(err.errorDescription ?: "创建视频失败")) }
                } catch (t: Throwable) {
                    mutateTask(taskId) { it.copy(phase = VideoTaskState.Phase.Failed(t.localizedMessage ?: "创建视频失败")) }
                }
            } catch (cancel: CancellationException) {
                removeTask(taskId)
                throw cancel
            } finally {
                staged?.let { f -> runCatching { f.delete() } }
                videoTaskHandles.remove(taskId)
            }
        }
    }

    private fun isoNow(): String =
        SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US)
            .apply { timeZone = TimeZone.getTimeZone("UTC") }
            .format(Date())
}
