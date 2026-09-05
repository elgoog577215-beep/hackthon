package com.mentorai.app.videoanalysis

import android.content.Context
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.mentorai.app.networking.AuthError
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.io.RandomAccessFile

/**
 * Drives the local-upload screen — mirrors iOS `VideoUploadViewModel`. Phases:
 *   Picking → Uploading(percent) → Creating → Done(videoId, videoName) | Failed(msg)
 *
 * Upload is chunked at 5 MB; we stage the content URI to a local cache file first so we can
 * seek/read predictably, then init/upload/finish and create the DB record UNSTARTED (no
 * auto-analysis — the detail page picks 云端 / 本地, mirroring iOS).
 */
class VideoUploadViewModel(
    private val context: Context,
    private val fileUri: Uri,
    private val pickedName: String,
    private val fileSize: Long,
    private val api: VideoAPI,
    private val tokenProvider: () -> String?,
) : ViewModel() {

    sealed class Phase {
        object Picking : Phase()
        data class Uploading(val percent: Int) : Phase()
        object Creating : Phase()
        data class Done(val videoId: String, val videoName: String) : Phase()
        data class Failed(val message: String) : Phase()
    }

    private val _phase = MutableStateFlow<Phase>(Phase.Picking)
    val phase: StateFlow<Phase> = _phase.asStateFlow()

    private val _videoName = MutableStateFlow(pickedName.substringBeforeLast('.', pickedName))
    val videoName: StateFlow<String> = _videoName.asStateFlow()

    val totalChunks: Int = ((fileSize + VideoAPI.CHUNK_SIZE - 1) / VideoAPI.CHUNK_SIZE).toInt().coerceAtLeast(1)
    private val _uploadedChunks = MutableStateFlow(0)
    val uploadedChunks: StateFlow<Int> = _uploadedChunks.asStateFlow()

    private var job: Job? = null

    val isBusy: Boolean
        get() = _phase.value is Phase.Uploading || _phase.value is Phase.Creating

    val canStart: Boolean
        get() = _phase.value is Phase.Picking && _videoName.value.trim().isNotEmpty()

    fun setVideoName(text: String) { _videoName.value = text }

    fun start() {
        if (!canStart) return
        val token = tokenProvider() ?: run {
            _phase.value = Phase.Failed("未登录")
            return
        }
        val trimmedName = _videoName.value.trim()
        if (trimmedName.isEmpty()) {
            _phase.value = Phase.Failed("请输入视频名称")
            return
        }
        _phase.value = Phase.Uploading(0)
        job = viewModelScope.launch {
            val staged: File = try {
                VideoAPI.stageUpload(context, fileUri, pickedName)
            } catch (t: Throwable) {
                _phase.value = Phase.Failed(t.localizedMessage ?: "无法读取所选视频")
                return@launch
            }
            try {
                val uploadId = api.initUpload(totalChunks, token)
                streamChunks(staged, uploadId, token)
                val result = api.finishUpload(uploadId, token)
                // Create the record UNSTARTED — no auto-analysis. The detail page lets the user
                // pick 云端 / 本地 (mirrors iOS). The cover is optional: pass it through nullable
                // rather than hard-failing when the server didn't produce one.
                _phase.value = Phase.Creating
                val newId = api.operate(
                    VideoOperationRequest(
                        operation = VideoOperation.Create,
                        name = trimmedName,
                        path = result.videoPath,
                        cover = result.coverPath,
                    ),
                    token,
                )
                _phase.value = Phase.Done(videoId = newId, videoName = trimmedName)
            } catch (err: AuthError) {
                _phase.value = Phase.Failed(err.errorDescription ?: "上传失败")
            } catch (t: Throwable) {
                _phase.value = Phase.Failed(t.localizedMessage ?: "上传失败")
            } finally {
                runCatching { staged.delete() }
            }
        }
    }

    fun cancel() {
        job?.cancel()
        job = null
        if (_phase.value is Phase.Uploading || _phase.value is Phase.Creating) {
            _phase.value = Phase.Failed("已取消")
        }
    }

    private suspend fun streamChunks(file: File, uploadId: String, token: String) {
        withContext(Dispatchers.IO) {
            RandomAccessFile(file, "r").use { raf ->
                val buffer = ByteArray(VideoAPI.CHUNK_SIZE)
                for (index in 0 until totalChunks) {
                    val read = raf.read(buffer)
                    if (read <= 0) break
                    val payload = if (read == buffer.size) buffer else buffer.copyOf(read)
                    api.uploadChunk(
                        uploadId = uploadId,
                        index = index,
                        data = payload,
                        filename = pickedName,
                        token = token,
                    )
                    _uploadedChunks.value = index + 1
                    // Reach 100 on the final chunk (matches iOS); the 合并/创建 steps follow.
                    val percent = ((index + 1) * 100 / totalChunks).coerceIn(0, 100)
                    _phase.value = Phase.Uploading(percent)
                }
            }
        }
    }
}
