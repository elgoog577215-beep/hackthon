package com.mentorai.app.chat

import com.mentorai.app.networking.APIClient

class SessionAPI(private val client: APIClient) {

    /** GET /session/list — summary list, no messages. */
    suspend fun list(token: String): List<ChatSession> =
        client.getEnvelope("/session/list", bearerToken = token)

    /** GET /session?id=... — full detail with messages. */
    suspend fun detail(id: String, token: String): ChatSession =
        client.getEnvelope("/session", mapOf("id" to id), token)

    /** DELETE /session/delete?id=... */
    suspend fun delete(id: String, token: String) {
        client.deleteEnvelope("/session/delete", mapOf("id" to id), token)
    }
}
