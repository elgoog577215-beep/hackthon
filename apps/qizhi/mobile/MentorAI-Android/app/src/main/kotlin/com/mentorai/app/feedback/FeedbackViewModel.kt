package com.mentorai.app.feedback

import android.content.Context
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.mentorai.app.chat.AttachmentAPI
import com.mentorai.app.chat.AttachmentLimits
import com.mentorai.app.networking.AuthError
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.UUID

/**
 * Drives the Android Feedback screen. Mirrors the iOS `FeedbackViewModel`:
 * star + content + optional attachments → POST /feedback.
 *
 * Attachments share the chat uploader: each item is appended in `.Uploading` state, then a
 * background job flips it to `.Done(path)` (path goes into `image_paths`) or `.Error(message)`.
 */
class FeedbackViewModel(
    private val feedbackApi: FeedbackAPI,
    private val attachmentApi: AttachmentAPI,
    private val tokenProvider: () -> String?,
) : ViewModel() {

    private val _star = MutableStateFlow(0)
    val star: StateFlow<Int> = _star.asStateFlow()

    private val _content = MutableStateFlow("")
    val content: StateFlow<String> = _content.asStateFlow()

    private val _attachments = MutableStateFlow<List<FeedbackAttachment>>(emptyList())
    val attachments: StateFlow<List<FeedbackAttachment>> = _attachments.asStateFlow()

    private val _isSubmitting = MutableStateFlow(false)
    val isSubmitting: StateFlow<Boolean> = _isSubmitting.asStateFlow()

    private val _submitMessage = MutableStateFlow<String?>(null)
    val submitMessage: StateFlow<String?> = _submitMessage.asStateFlow()

    private val _submitIsError = MutableStateFlow(false)
    val submitIsError: StateFlow<Boolean> = _submitIsError.asStateFlow()

    private val _starError = MutableStateFlow<String?>(null)
    val starError: StateFlow<String?> = _starError.asStateFlow()

    private val _contentError = MutableStateFlow<String?>(null)
    val contentError: StateFlow<String?> = _contentError.asStateFlow()

    private val _attachmentError = MutableStateFlow<String?>(null)
    val attachmentError: StateFlow<String?> = _attachmentError.asStateFlow()

    private val _didSucceed = MutableStateFlow(false)
    val didSucceed: StateFlow<Boolean> = _didSucceed.asStateFlow()

    private val uploadJobs = mutableMapOf<UUID, Job>()

    fun setStar(value: Int) {
        _star.value = value
        if (value in 1..5) _starError.value = null
    }

    fun setContent(value: String) {
        _content.value = value
        if (value.isNotBlank()) _contentError.value = null
    }

    val isUploadingAnyAttachment: Boolean
        get() = _attachments.value.any { it.isUploading }

    /** Submit is enabled when star + content are present, no uploads are in flight. */
    val canSubmit: Boolean
        get() = _star.value in 1..5 &&
            _content.value.trim().isNotEmpty() &&
            !_isSubmitting.value &&
            !isUploadingAnyAttachment

    fun addAttachment(context: Context, uri: Uri, filename: String, sizeBytes: Long) {
        _attachmentError.value = null

        if (_attachments.value.size >= FEEDBACK_MAX_ATTACHMENTS) {
            _attachmentError.value = "最多只能上传 $FEEDBACK_MAX_ATTACHMENTS 个附件"
            return
        }
        if (!AttachmentLimits.isAllowed(filename)) {
            _attachmentError.value = "不支持的文件类型：$filename"
            return
        }

        val attachment = FeedbackAttachment(
            localUri = uri,
            filename = filename,
            sizeBytes = sizeBytes,
            status = FeedbackAttachment.Status.Uploading,
        )
        _attachments.update { it + attachment }

        val token = tokenProvider()
        if (token.isNullOrBlank()) {
            updateAttachment(attachment.id, FeedbackAttachment.Status.Error("未登录"))
            return
        }

        val job = viewModelScope.launch {
            try {
                val path = attachmentApi.upload(context, uri, filename, token)
                updateAttachment(attachment.id, FeedbackAttachment.Status.Done(path))
            } catch (cancel: CancellationException) {
                removeAttachment(attachment.id)
                throw cancel
            } catch (err: AuthError) {
                updateAttachment(
                    attachment.id,
                    FeedbackAttachment.Status.Error(err.errorDescription ?: "上传失败"),
                )
            } catch (other: Throwable) {
                updateAttachment(
                    attachment.id,
                    FeedbackAttachment.Status.Error(other.localizedMessage ?: "上传失败"),
                )
            } finally {
                uploadJobs.remove(attachment.id)
            }
        }
        uploadJobs[attachment.id] = job
    }

    fun removeAttachment(id: UUID) {
        uploadJobs.remove(id)?.cancel()
        _attachments.update { list -> list.filterNot { it.id == id } }
    }

    private fun updateAttachment(id: UUID, status: FeedbackAttachment.Status) {
        _attachments.update { list ->
            list.map { if (it.id == id) it.copy(status = status) else it }
        }
    }

    /** Validate + submit. Sets [didSucceed] on success so the caller can dismiss the screen. */
    fun submit() {
        if (_isSubmitting.value) return
        _submitMessage.value = null
        _submitIsError.value = false
        _starError.value = null
        _contentError.value = null
        _attachmentError.value = null

        val trimmed = _content.value.trim()
        val starOk = _star.value in 1..5
        val contentOk = trimmed.isNotEmpty()
        if (!starOk) _starError.value = "请先选择评分（1–5 星）"
        if (!contentOk) _contentError.value = "请填写反馈与建议后再提交"
        if (!starOk || !contentOk) return

        val token = tokenProvider()
        if (token.isNullOrBlank()) {
            _submitIsError.value = true
            _submitMessage.value = "未登录"
            return
        }

        val imagePaths = _attachments.value.mapNotNull { it.remotePath }
        val request = SubmitFeedbackRequest(
            star = _star.value,
            content = trimmed,
            imagePaths = imagePaths.ifEmpty { null },
        )

        _isSubmitting.value = true
        viewModelScope.launch {
            try {
                feedbackApi.submit(request, token)
                _submitIsError.value = false
                _submitMessage.value = "提交成功，感谢您的反馈"
                _didSucceed.value = true
            } catch (err: AuthError) {
                _submitIsError.value = true
                _submitMessage.value = err.errorDescription ?: "提交失败"
            } catch (other: Throwable) {
                _submitIsError.value = true
                _submitMessage.value = other.localizedMessage ?: "提交失败"
            } finally {
                _isSubmitting.value = false
            }
        }
    }
}
