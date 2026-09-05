package com.mentorai.app.videoanalysis

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.mentorai.app.networking.AuthError
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.UUID

/**
 * Drives the Zhiyun import screen. Mirrors iOS `ZhiyunImportViewModel` — searching → picking →
 * importing → done | failed. The imported video is created UNSTARTED (no auto-analysis); the
 * detail page picks 云端 / 本地. The list-scoped [VideoListViewModel.startZhiyunImport] is the
 * foreground-continue variant that survives this screen closing.
 */
class ZhiyunImportViewModel(
    private val api: VideoAPI,
    private val tokenProvider: () -> String?,
) : ViewModel() {

    sealed class Phase {
        object Idle : Phase()
        object Searching : Phase()
        data class Picking(val courses: List<ZhiyunCourse>) : Phase()
        data class Importing(val percent: Int) : Phase()
        data class Done(val videoId: String, val courseName: String) : Phase()
        data class Failed(val message: String) : Phase()
    }

    private val isoDate = SimpleDateFormat("yyyy-MM-dd", Locale.US).apply {
        timeZone = TimeZone.getDefault()
    }

    private val _phase = MutableStateFlow<Phase>(Phase.Idle)
    val phase: StateFlow<Phase> = _phase.asStateFlow()

    private val _beginDate = MutableStateFlow<Date>(
        Calendar.getInstance().apply { add(Calendar.DAY_OF_YEAR, -7) }.time
    )
    val beginDate: StateFlow<Date> = _beginDate.asStateFlow()

    private val _endDate = MutableStateFlow<Date>(Date())
    val endDate: StateFlow<Date> = _endDate.asStateFlow()

    private val _courseNameFilter = MutableStateFlow("")
    val courseNameFilter: StateFlow<String> = _courseNameFilter.asStateFlow()

    private var importJob: Job? = null

    fun setBeginDate(date: Date) { _beginDate.value = date }
    fun setEndDate(date: Date) { _endDate.value = date }
    fun setCourseNameFilter(text: String) { _courseNameFilter.value = text }

    fun searchCourses() {
        val token = tokenProvider() ?: run {
            _phase.value = Phase.Failed("未登录")
            return
        }
        _phase.value = Phase.Searching
        viewModelScope.launch {
            try {
                val rows = api.listZhiyunCourses(
                    beginDate = isoDate.format(_beginDate.value),
                    endDate = isoDate.format(_endDate.value),
                    courseName = _courseNameFilter.value,
                    token = token,
                )
                _phase.value = Phase.Picking(rows)
            } catch (err: AuthError) {
                _phase.value = Phase.Failed(err.errorDescription ?: "查询失败")
            } catch (t: Throwable) {
                _phase.value = Phase.Failed(t.localizedMessage ?: "查询失败")
            }
        }
    }

    fun startImport(course: ZhiyunCourse) {
        val token = tokenProvider() ?: run {
            _phase.value = Phase.Failed("未登录")
            return
        }
        _phase.value = Phase.Importing(0)
        // Match the server's name composition ("课程名 + 章节") so the optimistic row groups
        // under the right course in the list. This is the iOS fix we already learned.
        val displayName = listOf(course.courseName.trim(), course.subTitle.trim())
            .filter { it.isNotEmpty() }
            .joinToString(" ")
        // Per-import marker so a cancel can notify the backend (see VideoAPI.cancelZhiyunImport).
        val importId = UUID.randomUUID().toString()
        importJob = viewModelScope.launch {
            try {
                var lastId: String? = null
                var failed = false
                api.importZhiyun(course.courseId, course.subId, importId, token).collect { event ->
                    when (event) {
                        is VideoAPI.ZhiyunImportEvent.Start ->
                            lastId = event.videoId
                        is VideoAPI.ZhiyunImportEvent.Progress ->
                            _phase.value = Phase.Importing(event.percent)
                        is VideoAPI.ZhiyunImportEvent.Error -> {
                            _phase.value = Phase.Failed(event.message)
                            failed = true
                        }
                        is VideoAPI.ZhiyunImportEvent.End ->
                            lastId = event.videoId ?: lastId
                    }
                }
                if (failed) return@launch
                val id = lastId
                if (id.isNullOrEmpty()) {
                    _phase.value = Phase.Failed("导入完成但缺少视频 ID")
                    return@launch
                }
                // Create the video UNSTARTED — no auto-analysis. The detail page picks 云端 / 本地
                // (mirrors iOS).
                _phase.value = Phase.Done(videoId = id, courseName = displayName)
            } catch (err: AuthError) {
                _phase.value = Phase.Failed(err.errorDescription ?: "导入失败")
            } catch (t: Throwable) {
                _phase.value = Phase.Failed(t.localizedMessage ?: "导入失败")
            }
        }
    }

    fun cancel() {
        importJob?.cancel()
        importJob = null
    }
}
