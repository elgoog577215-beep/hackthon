package com.mentorai.app.chat

import com.mentorai.app.networking.APIClient
import com.mentorai.app.networking.AuthError
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.emitAll
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.mapNotNull
import kotlinx.coroutines.flow.transformWhile
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

class ChatAPI(private val client: APIClient) {

    /**
     * POST /ai/chat — server replies with SSE. We build the request manually (POST + JSON
     * body + Accept: text/event-stream) and bridge OkHttp-SSE to a Flow of `ChatEvent`.
     *
     * Path matches the backend route (server `api/ai.py`, mounted under `/ai`) and the web
     * client (`postStream('/ai/chat', …)`). The request body shape already matched; the old
     * `/chat/send` path 404'd on this backend.
     */
    fun send(request: ChatSendRequest, token: String): Flow<ChatEvent> = flow {
        val payload = client.json.encodeToString(ChatSendRequest.serializer(), request)
        val httpRequest = client.buildRequest(
            method = "POST",
            path = "/ai/chat",
            body = client.jsonBody(payload),
            bearerToken = token,
            accept = "text/event-stream",
        )
        // Mirror iOS Chat/ChatAPI.swift: break on the first End/Error frame so a trailing error
        // followed by extra frames is never forwarded. transformWhile emits the terminal event,
        // then halts the upstream SSE collection.
        emitAll(
            SSEStream.messages(httpRequest, client.httpClient)
                .mapNotNull { sse -> SSEStream.parseChatEvent(sse, client.json) }
                .transformWhile { event ->
                    emit(event)
                    event !is ChatEvent.End && event !is ChatEvent.Error
                },
        )
    }
}
