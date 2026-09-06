package com.mentorai.app.user

import com.mentorai.app.networking.APIClient

class UserAPI(private val client: APIClient) {
    /** GET /user/current — returns the currently authenticated user (matches the iOS path). */
    suspend fun current(token: String): UserProfile =
        client.getEnvelope("/user/current", bearerToken = token)
}
