package com.mentorai.app.networking

import kotlinx.serialization.Serializable

/**
 * Mirrors the iOS `APIEnvelope` — every backend response is wrapped in this shape.
 * `success` may be omitted on some endpoints, so we default to "success unless explicitly false."
 */
@Serializable
data class APIEnvelope<T>(
    val success: Boolean? = null,
    val code: Int? = null,
    val error: String? = null,
    val message: String? = null,
    val data: T? = null,
) {
    val isSuccess: Boolean get() = success != false

    val errorMessage: String?
        get() = listOf(error, message).firstOrNull { !it.isNullOrBlank() }
}
