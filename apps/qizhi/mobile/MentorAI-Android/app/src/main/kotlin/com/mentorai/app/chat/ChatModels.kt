package com.mentorai.app.chat

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Wire models for chat — match the iOS Codable types and the backend pydantic schemas.
 * Field-name aliases are handled via @SerialName; defaults make decoding tolerant of missing
 * fields, mirroring the iOS `decodeIfPresent ?? default` style.
 */
@Serializable
enum class ChatRole {
    @SerialName("user") User,
    @SerialName("assistant") Assistant,
    @SerialName("system") System,
}

@Serializable
data class ChatMessage(
    val role: ChatRole = ChatRole.Assistant,
    val type: String = "text",
    val content: String = "",
    @SerialName("session_id") val sessionId: String? = null,
)

@Serializable
data class ChatSession(
    val id: String = "",
    val title: String = "",
    @SerialName("create_time") val createTime: String = "",
    @SerialName("update_time") val updateTime: String = "",
    val messages: List<ChatMessage> = emptyList(),
) {
    val displayTitle: String get() = if (title.isBlank()) "新对话" else title
    val sortKey: String get() = if (updateTime.isBlank()) createTime else updateTime
}

@Serializable
data class ChatSendRequest(
    val query: String,
    @SerialName("session_id") val sessionId: String? = null,
    @SerialName("file_paths") val filePaths: List<String>? = null,
    @SerialName("extra_params") val extraParams: Map<String, String>? = null,
)
