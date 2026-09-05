package com.mentorai.app.chat

import com.mentorai.app.networking.AuthError
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources

/** Single SSE message — mirrors iOS `SSEMessage`. `data` already has multi-line joins applied. */
data class SSEMessage(val event: String?, val data: String)

/**
 * Bridges OkHttp-SSE to a Kotlin Flow + parses message payloads into typed `ChatEvent`s.
 *
 * `messages(request, client)` exposes the raw stream so non-chat consumers can reuse it (the
 * Zhiyun import + future video analyze stream). `parseChatEvent` mirrors the iOS extraction
 * logic — be tolerant of slight schema drift (type vs event, content vs delta vs text).
 */
object SSEStream {

    /** Stream raw SSE messages from `request`. Errors propagate as Flow exceptions. */
    fun messages(request: Request, httpClient: OkHttpClient): Flow<SSEMessage> = callbackFlow {
        val factory = EventSources.createFactory(httpClient)
        val source = factory.newEventSource(request, object : EventSourceListener() {
            override fun onOpen(eventSource: EventSource, response: Response) {
                val ct = response.header("Content-Type").orEmpty()
                if (!ct.contains("text/event-stream", ignoreCase = true)) {
                    val body = runCatching { response.body?.string() }.getOrNull().orEmpty()
                    val err = if (response.code == 401) AuthError.Unauthorized
                    else AuthError.Server(response.code, body.take(500).ifBlank { null })
                    close(err)
                }
            }

            override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
                trySend(SSEMessage(event = type, data = data))
            }

            override fun onClosed(eventSource: EventSource) {
                close()
            }

            override fun onFailure(eventSource: EventSource, t: Throwable?, response: Response?) {
                if (response != null && !response.isSuccessful) {
                    val body = runCatching { response.body?.string() }.getOrNull().orEmpty()
                    val err = if (response.code == 401) AuthError.Unauthorized
                    else AuthError.Server(response.code, body.take(500).ifBlank { null })
                    close(err)
                    return
                }
                close(t ?: AuthError.Transport("SSE 连接失败"))
            }
        })
        awaitClose { source.cancel() }
    }

    /** Parse one SSE frame into a `ChatEvent`. Returns null if the frame isn't actionable. */
    fun parseChatEvent(message: SSEMessage, json: Json): ChatEvent? {
        val parsed: JsonElement? = runCatching { json.parseToJsonElement(message.data) }.getOrNull()
        val payloadEvent = eventNameFrom(parsed)
        val resolved = payloadEvent
            ?: message.event?.trim()?.lowercase()?.takeIf { it.isNotEmpty() }
            ?: inferEventName(parsed, message.data)

        return when (resolved) {
            "start" -> sessionIdFrom(parsed)?.let { ChatEvent.Start(it) }
            "loading" -> ChatEvent.Loading(extractStatusText(parsed, message.data))
            "thinking" -> ChatEvent.Thinking(extractStatusText(parsed, message.data))
            "message", "chunk" -> {
                val content = extractMessageContent(parsed, message.data)
                if (content.isNullOrEmpty()) null else ChatEvent.Message(content)
            }
            "card" -> ChatEvent.Card(message.data)
            "error" -> ChatEvent.Error(extractErrorMessage(parsed, message.data))
            "end", "done" -> ChatEvent.End
            "step" -> null
            else -> null
        }
    }

    private fun eventNameFrom(json: JsonElement?): String? {
        val obj = json as? JsonObject ?: return null
        return firstString(obj, listOf("type", "event"))
            ?.trim()
            ?.lowercase()
            ?.takeIf { it.isNotEmpty() }
    }

    private fun inferEventName(json: JsonElement?, raw: String): String {
        if (sessionIdFrom(json) != null) return "start"
        if (hasErrorPayload(json)) return "error"
        if (extractMessageContent(json, "")?.isNotEmpty() == true ||
            (json == null && raw.isNotEmpty())
        ) return "message"
        return ""
    }

    private fun sessionIdFrom(json: JsonElement?): String? {
        for (dict in candidateDictionaries(json)) {
            firstString(dict, listOf("session_id", "sessionId"))?.let { if (it.isNotEmpty()) return it }
        }
        return null
    }

    private fun extractMessageContent(json: JsonElement?, raw: String): String? {
        if (json is JsonPrimitive && json.isString) return json.content
        for (dict in candidateDictionaries(json)) {
            firstString(dict, listOf("content", "delta", "text"))?.let { return it }
        }
        return raw.ifEmpty { null }
    }

    private fun extractErrorMessage(json: JsonElement?, raw: String): String {
        if (json is JsonPrimitive && json.isString && json.content.isNotEmpty()) return json.content
        for (dict in candidateDictionaries(json)) {
            firstString(dict, listOf("error", "message", "detail"))?.let { if (it.isNotEmpty()) return it }
        }
        return raw.ifEmpty { "流式响应错误" }
    }

    private fun hasErrorPayload(json: JsonElement?): Boolean {
        for (dict in candidateDictionaries(json)) {
            firstString(dict, listOf("error"))?.let { return true }
        }
        return false
    }

    private fun candidateDictionaries(json: JsonElement?): List<JsonObject> {
        val root = json as? JsonObject ?: return emptyList()
        val out = mutableListOf(root)
        for (k in listOf("data", "payload", "content")) {
            (root[k] as? JsonObject)?.let { out.add(it) }
        }
        return out
    }

    private fun firstString(obj: JsonObject, keys: List<String>): String? {
        for (k in keys) {
            val v = obj[k] as? JsonPrimitive ?: continue
            if (v.isString) v.content.takeIf { it.isNotEmpty() }?.let { return it }
        }
        return null
    }

    private fun extractStatusText(json: JsonElement?, raw: String): String {
        if (json is JsonPrimitive && json.isString) {
            val s = json.content.trim()
            if (s.isNotEmpty()) return s
        }
        for (dict in candidateDictionaries(json)) {
            firstString(
                dict,
                listOf("message", "status", "label", "text", "detail", "description", "title", "content"),
            )?.let { return it }
            val step = (dict["step"] as? JsonPrimitive)?.intOrNull
            if (step != null) {
                val total = (dict["total"] as? JsonPrimitive)?.intOrNull
                return if (total != null && total > 0) "处理进度 $step/$total" else "步骤 $step"
            }
        }
        if (json == null && raw.isNotEmpty()) return raw
        return ""
    }
}
