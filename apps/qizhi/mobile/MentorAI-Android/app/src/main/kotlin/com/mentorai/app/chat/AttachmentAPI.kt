package com.mentorai.app.chat

import android.content.Context
import android.net.Uri
import com.mentorai.app.networking.APIClient
import com.mentorai.app.networking.AuthError
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import java.io.FileOutputStream
import java.util.UUID

/**
 * POST /attachment/upload — multipart upload that returns the server-side `path` to attach to
 * the next /chat/send. Mirrors the iOS `AttachmentAPI.upload`.
 *
 * Content URIs may not point at a real file; we copy them into the cache directory first so
 * OkHttp can stream them with a stable filename.
 */
class AttachmentAPI(private val client: APIClient) {

    suspend fun upload(context: Context, uri: Uri, filename: String, token: String): String =
        withContext(Dispatchers.IO) {
            val cached = copyToCache(context, uri, filename)
            try {
                val mime = context.contentResolver.getType(uri) ?: "application/octet-stream"
                val body = MultipartBody.Builder()
                    .setType(MultipartBody.FORM)
                    .addFormDataPart(
                        name = "file",
                        filename = filename,
                        body = cached.asRequestBody(mime.toMediaTypeOrNull()),
                    )
                    .build()
                val request = client.buildRequest(
                    method = "POST",
                    path = "/attachment/upload",
                    body = body,
                    bearerToken = token,
                )
                val path: String = client.decodeEnvelope(request)
                path
            } finally {
                runCatching { cached.delete() }
            }
        }

    private fun copyToCache(context: Context, uri: Uri, filename: String): File {
        val safe = filename.ifBlank { "upload" }
        val ext = safe.substringAfterLast('.', "")
        val name = "upload-${UUID.randomUUID()}${if (ext.isNotEmpty()) ".$ext" else ""}"
        val out = File(context.cacheDir, name)
        context.contentResolver.openInputStream(uri).use { input ->
            requireNotNull(input) { "Cannot open attachment URI: $uri" }
            FileOutputStream(out).use { sink -> input.copyTo(sink) }
        }
        if (!out.exists() || out.length() == 0L) {
            throw AuthError.Transport("无法读取所选文件")
        }
        return out
    }
}
