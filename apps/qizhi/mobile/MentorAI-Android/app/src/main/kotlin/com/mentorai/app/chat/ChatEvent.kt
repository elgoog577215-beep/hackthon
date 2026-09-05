package com.mentorai.app.chat

/**
 * One typed event per SSE message kind we care about. Mirrors the iOS `ChatEvent` enum.
 * The view model dispatches on this; everything else (raw JSON, transport details) is hidden
 * inside `SSEStream`.
 */
sealed class ChatEvent {
    data class Start(val sessionId: String) : ChatEvent()
    data class Loading(val text: String) : ChatEvent()
    data class Thinking(val text: String) : ChatEvent()
    data class Message(val content: String) : ChatEvent()
    data class Card(val payload: String) : ChatEvent()
    data class Error(val message: String) : ChatEvent()
    object End : ChatEvent()
}
