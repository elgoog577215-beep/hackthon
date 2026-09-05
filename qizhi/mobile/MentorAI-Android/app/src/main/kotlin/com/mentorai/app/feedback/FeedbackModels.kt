package com.mentorai.app.feedback

import android.net.Uri
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import java.util.Locale
import java.util.UUID

/**
 * Mirrors the server `SubmitFeedbackParams`. `imagePaths` are the storage paths returned by
 * `/attachment/upload` — same endpoint chat uses — so the feedback flow reuses [AttachmentAPI]
 * instead of inventing its own uploader.
 */
@Serializable
data class SubmitFeedbackRequest(
    val star: Int,
    val content: String,
    @SerialName("image_paths") val imagePaths: List<String>? = null,
)

/**
 * Local attachment state shown in the feedback sheet — same lifecycle pattern as
 * `ChatAttachment`: `Uploading → Done(path)` or `Uploading → Error(msg)`.
 */
data class FeedbackAttachment(
    val id: UUID = UUID.randomUUID(),
    val localUri: Uri,
    val filename: String,
    val sizeBytes: Long,
    val status: Status,
) {
    val remotePath: String? get() = (status as? Status.Done)?.path
    val isUploading: Boolean get() = status is Status.Uploading
    val fileExtension: String
        get() = filename.substringAfterLast('.', "").lowercase(Locale.US)

    val displaySize: String get() = formatBytes(sizeBytes)

    sealed class Status {
        object Uploading : Status()
        data class Done(val path: String) : Status()
        data class Error(val message: String) : Status()
    }

    private companion object {
        fun formatBytes(bytes: Long): String {
            if (bytes <= 0) return "0 B"
            val units = arrayOf("B", "KB", "MB", "GB")
            var size = bytes.toDouble()
            var idx = 0
            while (size >= 1024 && idx < units.size - 1) {
                size /= 1024
                idx++
            }
            return String.format(Locale.US, if (size >= 100) "%.0f %s" else "%.1f %s", size, units[idx])
        }
    }
}

/** Max attachments per submission — matches the web's `maxAttachments`. */
const val FEEDBACK_MAX_ATTACHMENTS: Int = 5
