package com.mentorai.app.chat

import android.net.Uri
import java.util.Locale
import java.util.UUID

/**
 * UI-side attachment representation, mirroring the iOS `ChatAttachment`. The lifecycle is
 * `Uploading → Done(path)` or `Uploading → Error(msg)`; the ViewModel uses `remotePath` to
 * decide whether the message is ready to send.
 */
data class ChatAttachment(
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

/** Mirror of iOS `AttachmentLimits.isAllowed` — keeps the picker honest. */
object AttachmentLimits {
    private val allowed = setOf(
        "pdf", "txt", "md", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
        "jpg", "jpeg", "png", "gif", "webp", "bmp", "svg",
        "mp4", "mov", "webm", "mkv", "avi", "m4v",
    )

    fun isAllowed(filename: String): Boolean {
        val ext = filename.substringAfterLast('.', "").lowercase(Locale.US)
        return ext.isNotEmpty() && (ext in allowed)
    }
}
