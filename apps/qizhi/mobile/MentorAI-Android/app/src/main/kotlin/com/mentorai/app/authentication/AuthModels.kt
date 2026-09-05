package com.mentorai.app.authentication

import com.mentorai.app.user.UserProfile
import kotlinx.serialization.Serializable

@Serializable
data class AuthSession(
    val accessToken: String,
    val user: UserProfile? = null,
)

/** Server response for /auth/url — either a bare URL string in `data`, or a wrapped object. */
@Serializable
data class AuthorizationURLPayload(
    val redirect_url: String? = null,
    val url: String? = null,
    val authorize_url: String? = null,
    val authorizeUrl: String? = null,
    val state: String? = null,
) {
    val resolvedUrl: String?
        get() = listOf(redirect_url, url, authorize_url, authorizeUrl).firstOrNull { !it.isNullOrBlank() }
}
