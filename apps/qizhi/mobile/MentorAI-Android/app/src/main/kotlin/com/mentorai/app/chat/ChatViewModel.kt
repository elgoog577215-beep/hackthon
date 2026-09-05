package com.mentorai.app.chat

import android.content.Context
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.mentorai.app.networking.AuthError
import com.mentorai.app.support.decodingJsonEscapes
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.transformWhile
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.UUID

/**
 * One per chat detail screen. Mirrors iOS `ChatViewModel` — load history, send + stream replies,
 * manage attachments, decode streamed JSON escapes when the stream ends.
 */
class ChatViewModel(
    val initialSessionId: String?,
    private val chatApi: ChatAPI,
    private val sessionApi: SessionAPI,
    private val attachmentApi: AttachmentAPI,
    private val tokenProvider: () -> String?,
) : ViewModel() {

    private val _session = MutableStateFlow<ChatSession?>(null)
    val session: StateFlow<ChatSession?> = _session.asStateFlow()

    private val _messages = MutableStateFlow<List<ChatMessage>>(emptyList())
    val messages: StateFlow<List<ChatMessage>> = _messages.asStateFlow()

    private val _draft = MutableStateFlow("")
    val draft: StateFlow<String> = _draft.asStateFlow()

    private val _statusText = MutableStateFlow<String?>(null)
    val statusText: StateFlow<String?> = _statusText.asStateFlow()

    private val _isStreaming = MutableStateFlow(false)
    val isStreaming: StateFlow<Boolean> = _isStreaming.asStateFlow()

    private val _streamError = MutableStateFlow<String?>(null)
    val streamError: StateFlow<String?> = _streamError.asStateFlow()

    private val _isLoadingSession = MutableStateFlow(false)
    val isLoadingSession: StateFlow<Boolean> = _isLoadingSession.asStateFlow()

    private val _sessionError = MutableStateFlow<String?>(null)
    val sessionError: StateFlow<String?> = _sessionError.asStateFlow()

    private val _attachments = MutableStateFlow<List<ChatAttachment>>(emptyList())
    val attachments: StateFlow<List<ChatAttachment>> = _attachments.asStateFlow()

    private var streamJob: Job? = null
    private val uploadJobs = mutableMapOf<UUID, Job>()

    val currentSessionId: String? get() = _session.value?.id ?: initialSessionId

    val titleForDisplay: String
        get() = _session.value?.title?.takeIf { it.isNotBlank() }
            ?: if (initialSessionId == null) "新对话" else "对话"

    val canSend: Boolean
        get() {
            val hasText = _draft.value.trim().isNotEmpty()
            val hasDoneAttachment = _attachments.value.any { it.remotePath != null }
            val anyUploading = _attachments.value.any { it.isUploading }
            return !_isStreaming.value && !anyUploading && (hasText || hasDoneAttachment)
        }

    val isUploadingAnyAttachment: Boolean
        get() = _attachments.value.any { it.isUploading }

    fun setDraft(text: String) { _draft.value = text }
    fun setStreamError(msg: String?) { _streamError.value = msg }

    /** Non-suspending convenience for buttons (Retry, etc.). */
    fun retryLoad() {
        viewModelScope.launch { load() }
    }

    suspend fun load() {
        val id = initialSessionId ?: return
        val token = tokenProvider() ?: run {
            _sessionError.value = "未登录"
            return
        }
        _isLoadingSession.value = true
        _sessionError.value = null
        try {
            val detail = sessionApi.detail(id, token)
            _session.value = detail
            _messages.value = detail.messages
        } catch (err: AuthError) {
            _sessionError.value = err.errorDescription
        } catch (t: Throwable) {
            _sessionError.value = t.localizedMessage ?: "加载失败"
        } finally {
            _isLoadingSession.value = false
        }
    }

    fun send() {
        if (_isStreaming.value || isUploadingAnyAttachment) return
        val text = _draft.value.trim()
        val doneAttachments = _attachments.value.filter { it.remotePath != null }
        val donePaths = doneAttachments.mapNotNull { it.remotePath }
        if (text.isEmpty() && donePaths.isEmpty()) return
        val token = tokenProvider() ?: run {
            _streamError.value = "未登录"
            return
        }

        _draft.value = ""
        _streamError.value = null
        _statusText.value = null

        val userBubble = composeUserBubble(text, doneAttachments)
        _messages.update { it + ChatMessage(role = ChatRole.User, content = userBubble) }
        _messages.update { it + ChatMessage(role = ChatRole.Assistant, content = "") }
        val assistantIndex = _messages.value.size - 1
        _isStreaming.value = true

        val request = ChatSendRequest(
            // Match iOS: omit session_id when nil OR empty (coerce a blank id to null).
            sessionId = currentSessionId?.takeIf { it.isNotEmpty() },
            query = composeQuery(text, doneAttachments),
            filePaths = donePaths.ifEmpty { null },
            extraParams = null,
        )
        _attachments.value = emptyList()

        streamJob = viewModelScope.launch {
            try {
                // Mirror iOS: handle each event, then STOP once an End or Error frame arrives
                // (transformWhile emits the terminal event, then halts the collect) instead of
                // relying solely on the server closing the stream.
                chatApi.send(request, token)
                    .transformWhile { event ->
                        emit(event)
                        event !is ChatEvent.End && event !is ChatEvent.Error
                    }
                    .collect { event -> handle(event, assistantIndex) }
            } catch (err: AuthError) {
                _streamError.value = err.errorDescription
            } catch (t: Throwable) {
                _streamError.value = t.localizedMessage ?: "流式响应失败"
            } finally {
                decodeAssistantTrailingEscapes(assistantIndex)
                _isStreaming.value = false
                _statusText.value = null
                streamJob = null
            }
        }
    }

    fun cancel() {
        streamJob?.cancel()
        streamJob = null
        _isStreaming.value = false
        _statusText.value = null
    }

    fun addAttachment(context: Context, uri: Uri, filename: String, size: Long) {
        if (!AttachmentLimits.isAllowed(filename)) {
            _streamError.value = "不支持的文件类型：$filename"
            return
        }
        val attachment = ChatAttachment(
            localUri = uri,
            filename = filename,
            sizeBytes = size,
            status = ChatAttachment.Status.Uploading,
        )
        _attachments.update { it + attachment }
        val id = attachment.id
        val token = tokenProvider()
        if (token.isNullOrBlank()) {
            updateAttachmentStatus(id, ChatAttachment.Status.Error("未登录"))
            return
        }
        uploadJobs[id] = viewModelScope.launch {
            try {
                val path = attachmentApi.upload(context, uri, filename, token)
                updateAttachmentStatus(id, ChatAttachment.Status.Done(path))
            } catch (err: AuthError) {
                updateAttachmentStatus(id, ChatAttachment.Status.Error(err.errorDescription ?: "上传失败"))
            } catch (t: Throwable) {
                updateAttachmentStatus(id, ChatAttachment.Status.Error(t.localizedMessage ?: "上传失败"))
            } finally {
                uploadJobs.remove(id)
            }
        }
    }

    fun removeAttachment(id: UUID) {
        uploadJobs.remove(id)?.cancel()
        _attachments.update { list -> list.filterNot { it.id == id } }
    }

    private fun updateAttachmentStatus(id: UUID, status: ChatAttachment.Status) {
        _attachments.update { list ->
            list.map { if (it.id == id) it.copy(status = status) else it }
        }
    }

    private fun handle(event: ChatEvent, assistantIndex: Int) {
        when (event) {
            is ChatEvent.Start -> {
                if (_session.value == null) {
                    _session.value = ChatSession(id = event.sessionId)
                }
            }
            is ChatEvent.Loading -> if (event.text.isNotEmpty()) _statusText.value = event.text
            is ChatEvent.Thinking -> if (event.text.isNotEmpty()) _statusText.value = event.text
            is ChatEvent.Message -> {
                _statusText.value = null
                appendAssistantChunk(assistantIndex, event.content)
            }
            is ChatEvent.Card -> Unit
            is ChatEvent.Error -> _streamError.value = event.message
            ChatEvent.End -> _statusText.value = null
        }
    }

    private fun appendAssistantChunk(index: Int, chunk: String) {
        _messages.update { list ->
            if (index !in list.indices) return@update list
            val target = list[index]
            list.toMutableList().also { it[index] = target.copy(content = target.content + chunk) }
        }
    }

    /**
     * Backend streams the raw final_answer slice from the model's JSON; literal "\n", "\"" etc.
     * survive to the client. Decode the assembled message once when the stream ends so the
     * persisted bubble shows real newlines / quotes / etc. — mirrors the iOS fix.
     */
    private fun decodeAssistantTrailingEscapes(index: Int) {
        _messages.update { list ->
            if (index !in list.indices) return@update list
            val target = list[index]
            if (target.role != ChatRole.Assistant) return@update list
            val decoded = target.content.decodingJsonEscapes()
            if (decoded == target.content) return@update list
            list.toMutableList().also { it[index] = target.copy(content = decoded) }
        }
    }

    /** Mirrors iOS `composeQuery` — append `[filename]` markers so the planner sees the files. */
    private fun composeQuery(text: String, attachments: List<ChatAttachment>): String {
        if (attachments.isEmpty()) return text
        val markers = attachments.joinToString(" ") { "[${it.filename}]" }
        return if (text.isEmpty()) markers else "$text\n\n$markers"
    }

    /** Mirrors iOS `composeUserBubble` — emoji + filenames stacked above the user text. */
    private fun composeUserBubble(text: String, attachments: List<ChatAttachment>): String {
        if (attachments.isEmpty()) return text
        val header = attachments.joinToString("\n") { "📎 ${it.filename}" }
        return if (text.isEmpty()) header else "$header\n\n$text"
    }
}
