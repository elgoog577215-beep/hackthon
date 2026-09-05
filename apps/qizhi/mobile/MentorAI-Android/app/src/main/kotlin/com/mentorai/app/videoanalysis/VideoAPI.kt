package com.mentorai.app.videoanalysis

import android.content.Context
import android.net.Uri
import com.mentorai.app.chat.SSEMessage
import com.mentorai.app.chat.SSEStream
import com.mentorai.app.networking.APIClient
import com.mentorai.app.networking.AuthError
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import java.io.FileOutputStream
import java.io.InputStream
import java.util.UUID

/**
 * Mirrors the iOS `VideoAPI`. REST methods use `APIClient` helpers; chunked upload and the
 * Zhiyun import stream talk to OkHttp directly so we can pump multipart bodies and SSE.
 */
class VideoAPI(private val client: APIClient) {

    // ---- List + detail + operations ----

    suspend fun list(token: String): List<VideoSummary> =
        client.getEnvelope("/video/list", bearerToken = token)

    suspend fun detail(id: String, token: String): VideoDetail =
        client.getEnvelope("/video", mapOf("id" to id), token)

    /**
     * Kick off analysis for a video. `mode` selects 云端 (智云/超星) vs 本地 self-hosted model and
     * is sent as the `mode` query param (cloud|local), mirroring iOS `analyze(id:mode:token:)`.
     * Defaults to [AnalysisMode.Cloud]; param order (id, mode, token) matches iOS and the
     * detail-screen caller `analyze(d.id, mode, token)`.
     */
    suspend fun analyze(id: String, mode: AnalysisMode = AnalysisMode.Cloud, token: String) {
        // Returns ApiResponse[None]; we only care that it didn't error.
        val request = client.buildRequest(
            method = "GET",
            path = "/video/analyze",
            query = mapOf("id" to id, "mode" to mode.wireValue),
            bearerToken = token,
        )
        client.executeString(request)
    }

    /** Returns the new video id on Create, otherwise null. Mirrors iOS `VideoAPI.operate`. */
    suspend fun operate(params: VideoOperationRequest, token: String): String {
        val payload = client.json.encodeToString(VideoOperationRequest.serializer(), params)
        val request = client.buildRequest(
            method = "POST",
            path = "/video/operation",
            body = client.jsonBody(payload),
            bearerToken = token,
        )
        // The envelope's data is a string (the new id) on Create; otherwise null.
        val body = client.executeString(request)
        val env = client.json.parseToJsonElement(body) as? JsonObject
            ?: throw AuthError.Server(0, "无效的响应")
        if (env["success"]?.let { (it as? JsonPrimitive)?.booleanLiteral() } == false) {
            val msg = (env["error"] as? JsonPrimitive)?.contentOrNull
                ?: (env["message"] as? JsonPrimitive)?.contentOrNull
            throw AuthError.Server((env["code"] as? JsonPrimitive)?.intOrNull ?: 0, msg)
        }
        return (env["data"] as? JsonPrimitive)?.contentOrNull.orEmpty()
    }

    private fun JsonPrimitive.booleanLiteral(): Boolean? =
        if (isString) content.toBooleanStrictOrNull() else content.toBooleanStrictOrNull()

    // ---- Zhiyun (smart classroom) ----

    /**
     * The server returns groups; the iOS app flattens them to recording rows for display, and
     * applies the (optional) course-name filter client-side because the server dropped it.
     */
    suspend fun listZhiyunCourses(
        beginDate: String,
        endDate: String,
        courseName: String?,
        token: String,
    ): List<ZhiyunCourse> {
        val groups: List<ZhiyunCourseGroup> = client.getEnvelope(
            path = "/video/zhiyun/list",
            query = mapOf(
                "search_begin_date" to beginDate,
                "search_end_date" to endDate,
            ),
            bearerToken = token,
        )
        var rows = groups.flatMap { group ->
            group.items.map { item ->
                ZhiyunCourse(
                    courseId = group.courseId,
                    subId = item.subId,
                    courseName = group.courseName,
                    subTitle = item.subTitle,
                    teacherName = item.teacherName,
                    classBegin = item.classBegin,
                )
            }
        }
        val filter = courseName?.trim().orEmpty()
        if (filter.isNotEmpty()) {
            rows = rows.filter { it.courseName.contains(filter, ignoreCase = true) }
        }
        return rows
    }

    sealed class ZhiyunImportEvent {
        /** The server announces the new video id up-front via the `start` event: {"id": "..."}. */
        data class Start(val videoId: String) : ZhiyunImportEvent()
        data class Progress(val percent: Int) : ZhiyunImportEvent()
        data class Error(val message: String) : ZhiyunImportEvent()
        data class End(val videoId: String?) : ZhiyunImportEvent()
    }

    /**
     * GET /video/zhiyun/import?course_id=&sub_id=&import_id= — SSE with `start` + `loading` + `end`.
     * `importId` is echoed to the server so an out-of-band [cancelZhiyunImport] can stop the
     * download mid-flight (a cancelled client SSE alone is unreliable). Mirrors iOS
     * `importZhiyun(courseID:subID:importID:)`.
     */
    fun importZhiyun(courseId: String, subId: String, importId: String, token: String): Flow<ZhiyunImportEvent> = flow {
        val request = client.buildRequest(
            method = "GET",
            path = "/video/zhiyun/import",
            query = mapOf("course_id" to courseId, "sub_id" to subId, "import_id" to importId),
            bearerToken = token,
            accept = "text/event-stream",
        )
        SSEStream.messages(request, client.httpClient).collect { sse ->
            val event = parseZhiyunImport(sse) ?: return@collect
            emit(event)
        }
    }

    /**
     * 取消正在进行的智云课堂视频导入. Cancelling the client SSE alone is unreliable (proxies buffer
     * the upstream, so the backend only notices the disconnect after the download finished and the
     * video already landed in the DB — "取消后视频仍出现在列表里"). This writes an out-of-band cancel
     * marker so the backend stops at the next chunk and cleans up. Best-effort; mirrors iOS
     * `cancelZhiyunImport(importID:)`.
     */
    suspend fun cancelZhiyunImport(importId: String, token: String) {
        if (importId.isEmpty()) return
        val payload = buildJsonObject { put("import_id", importId) }.toString()
        val request = client.buildRequest(
            method = "POST",
            path = "/video/zhiyun/import/cancel",
            body = client.jsonBody(payload),
            bearerToken = token,
        )
        client.executeString(request)
    }

    private fun parseZhiyunImport(sse: SSEMessage): ZhiyunImportEvent? {
        val name = sse.event?.trim()?.lowercase()
        val payload = runCatching { client.json.parseToJsonElement(sse.data) }.getOrNull()
        val obj = payload as? JsonObject
        return when (name) {
            "start" -> {
                val id = (obj?.get("id") as? JsonPrimitive)?.contentOrNull?.takeIf { it.isNotEmpty() }
                    ?: return null
                ZhiyunImportEvent.Start(videoId = id)
            }
            "loading" -> {
                val p = (obj?.get("progress") as? JsonPrimitive)?.let {
                    it.intOrNull ?: it.doubleOrNull?.toInt()
                } ?: return null
                ZhiyunImportEvent.Progress(p.coerceIn(0, 100))
            }
            "error" -> {
                val msg = (obj?.get("error") as? JsonPrimitive)?.contentOrNull
                    ?: (obj?.get("message") as? JsonPrimitive)?.contentOrNull
                    ?: sse.data.ifEmpty { "导入失败" }
                ZhiyunImportEvent.Error(msg)
            }
            "end", "done" -> {
                val id = (obj?.get("id") as? JsonPrimitive)?.contentOrNull?.takeIf { it.isNotEmpty() }
                ZhiyunImportEvent.End(videoId = id)
            }
            else -> null
        }
    }

    // ---- Chunked upload ----

    /** Initialize a chunked upload with N chunks; returns the `upload_id`. */
    suspend fun initUpload(totalChunks: Int, token: String): String {
        val form = "chunks=$totalChunks"
        val id: String = client.postFormEnvelope("/video/init", form, token)
        if (id.isBlank()) throw AuthError.Server(0, "初始化上传失败")
        return id
    }

    /** Upload one 5 MB chunk via multipart. Mirrors iOS `uploadChunk`. */
    suspend fun uploadChunk(
        uploadId: String,
        index: Int,
        data: ByteArray,
        filename: String,
        token: String,
    ) {
        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("upload_id", uploadId)
            .addFormDataPart("index", index.toString())
            .addFormDataPart(
                name = "file",
                filename = filename,
                body = data.toRequestBody("application/octet-stream".toMediaType()),
            )
            .build()
        val request = client.buildRequest(
            method = "POST",
            path = "/video/upload",
            body = body,
            bearerToken = token,
        )
        // Envelope with `data: null` on success — just check non-error.
        client.executeString(request)
    }

    /** Finish the upload, asking the server to merge chunks. Returns the video + cover path. */
    suspend fun finishUpload(uploadId: String, token: String): UploadFinishResult {
        val body = client.formBody("upload_id=$uploadId")
        val request = client.buildRequest(
            method = "POST",
            path = "/video/finish",
            body = body,
            bearerToken = token,
        )
        val responseBody = client.executeString(request)
        val root = client.json.parseToJsonElement(responseBody) as? JsonObject
            ?: throw AuthError.Server(0, "合并上传失败")
        val data = root["data"] as? JsonObject ?: throw AuthError.Server(0, "合并上传失败")
        val path = (data["path"] as? JsonPrimitive)?.contentOrNull.orEmpty()
        val cover = (data["cover_path"] as? JsonPrimitive)?.contentOrNull
        if (path.isBlank()) throw AuthError.Server(0, "合并上传失败")
        return UploadFinishResult(videoPath = path, coverPath = cover)
    }

    companion object {
        const val CHUNK_SIZE: Int = 5 * 1024 * 1024  // 5 MB, matches iOS + web

        /**
         * Copy a content URI into the app cache so we can stream it predictably from disk
         * (URIs may not be seekable). Caller is responsible for deleting the returned file.
         */
        suspend fun stageUpload(context: Context, uri: Uri, fallbackName: String): File =
            withContext(Dispatchers.IO) {
                val ext = fallbackName.substringAfterLast('.', "mp4")
                val out = File(context.cacheDir, "upload-${UUID.randomUUID()}.$ext")
                context.contentResolver.openInputStream(uri).use { input: InputStream? ->
                    requireNotNull(input) { "无法读取所选视频" }
                    FileOutputStream(out).use { sink -> input.copyTo(sink) }
                }
                if (!out.exists() || out.length() == 0L) {
                    throw AuthError.Transport("无法读取所选视频")
                }
                out
            }
    }
}
