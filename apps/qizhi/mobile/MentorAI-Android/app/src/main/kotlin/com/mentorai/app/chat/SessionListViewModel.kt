package com.mentorai.app.chat

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.mentorai.app.networking.AuthError
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Holds the chat-sessions list. Mirrors iOS `SessionListViewModel` — refresh on demand, delete
 * by id with confirmation, surface errors when the list is empty.
 */
class SessionListViewModel(
    private val sessionApi: SessionAPI,
    private val tokenProvider: () -> String?,
) : ViewModel() {

    private val _sessions = MutableStateFlow<List<ChatSession>>(emptyList())
    val sessions: StateFlow<List<ChatSession>> = _sessions.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    fun refresh() {
        val token = tokenProvider() ?: return
        _isLoading.value = true
        _error.value = null
        viewModelScope.launch {
            try {
                // Mirror iOS: newest first by sortKey (update_time, falling back to create_time).
                _sessions.value = sessionApi.list(token).sortedByDescending { it.sortKey }
            } catch (err: AuthError) {
                _error.value = err.errorDescription
            } catch (t: Throwable) {
                _error.value = t.localizedMessage ?: "加载失败"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /** Mirrors iOS `upsert` — replace an existing session or insert a new one, then re-sort. */
    fun upsert(session: ChatSession) {
        val current = _sessions.value
        val idx = current.indexOfFirst { it.id == session.id }
        val updated = if (idx >= 0) {
            current.toMutableList().also { it[idx] = session }
        } else {
            current.toMutableList().also { it.add(0, session) }
        }
        _sessions.value = updated.sortedByDescending { it.sortKey }
    }

    /**
     * Optimistic delete, mirroring iOS `SessionListViewModel.delete`: drop the row immediately,
     * then call the API. On failure, re-insert it at the original index, re-sort, and surface the
     * error.
     */
    fun delete(id: String) {
        val token = tokenProvider()
        if (token.isNullOrBlank()) {
            _error.value = "未登录"
            return
        }
        val idx = _sessions.value.indexOfFirst { it.id == id }
        if (idx < 0) return
        val removed = _sessions.value[idx]
        _sessions.value = _sessions.value.toMutableList().also { it.removeAt(idx) }
        viewModelScope.launch {
            try {
                sessionApi.delete(id, token)
            } catch (err: AuthError) {
                _sessions.value = _sessions.value.toMutableList()
                    .also { it.add(idx, removed) }
                    .sortedByDescending { it.sortKey }
                _error.value = err.errorDescription
            } catch (t: Throwable) {
                _sessions.value = _sessions.value.toMutableList()
                    .also { it.add(idx, removed) }
                    .sortedByDescending { it.sortKey }
                _error.value = t.localizedMessage ?: "删除失败"
            }
        }
    }
}
