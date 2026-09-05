package com.mentorai.app.user

import com.mentorai.app.support.ServerDate
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Mirrors the iOS `UserProfile`: every field is optional because the backend may omit them.
 * Display fallbacks live in `displayName` / `formattedCreateTime`.
 */
@Serializable
data class UserProfile(
    val id: String? = null,
    @SerialName("zju_id") val zjuId: String? = null,
    val name: String? = null,
    val department: String? = null,
    val phone: String? = null,
    val email: String? = null,
    @SerialName("create_time") val createTime: String? = null,
) {
    val displayName: String
        get() = listOf(name, zjuId, id).firstOrNull { !it.isNullOrBlank() } ?: "—"

    val formattedCreateTime: String?
        get() = createTime?.takeIf { it.isNotBlank() }?.let { ServerDate.absolute(it) }
}
