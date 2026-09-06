package com.mentorai.app.app

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.mentorai.app.MentorAIApp
import com.mentorai.app.authentication.AuthService
import com.mentorai.app.authentication.AuthSession
import com.mentorai.app.networking.AuthError
import com.mentorai.app.user.UserProfile
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Mirrors iOS `AppState`: holds the launch / signedOut / signedIn phase, the cached user
 * profile, and exposes sign-in / sign-out methods. Backed by `StateFlow` so Compose recomposes
 * the right subtree when phase changes.
 */
class AppState(private val app: MentorAIApp) : ViewModel() {

    sealed class Phase {
        object Launching : Phase()
        object SignedOut : Phase()
        data class SignedIn(val session: AuthSession) : Phase()
    }

    private val _phase = MutableStateFlow<Phase>(Phase.Launching)
    val phase: StateFlow<Phase> = _phase.asStateFlow()

    private val _isAuthenticating = MutableStateFlow(false)
    val isAuthenticating: StateFlow<Boolean> = _isAuthenticating.asStateFlow()

    private val _loginError = MutableStateFlow<AuthError?>(null)
    val loginError: StateFlow<AuthError?> = _loginError.asStateFlow()

    private val _currentUser = MutableStateFlow<UserProfile?>(null)
    val currentUser: StateFlow<UserProfile?> = _currentUser.asStateFlow()

    private val _isLoadingProfile = MutableStateFlow(false)
    val isLoadingProfile: StateFlow<Boolean> = _isLoadingProfile.asStateFlow()

    private val _profileError = MutableStateFlow<String?>(null)
    val profileError: StateFlow<String?> = _profileError.asStateFlow()

    /**
     * Whether the current session was created via "暂不登录" (skip login / test mode). Persisted
     * across launches like iOS (`UserDefaults` key `com.mentorai.app.isTestMode`) and restored on
     * bootstrap, so a resumed test session is still recognised. Video screens gate the 智云 source
     * on this. Observable so Compose recomposes when it flips.
     */
    private val prefs = app.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    private val _isTestMode = MutableStateFlow(prefs.getBoolean(KEY_IS_TEST_MODE, false))
    val isTestMode: StateFlow<Boolean> = _isTestMode.asStateFlow()

    private fun setTestMode(value: Boolean) {
        _isTestMode.value = value
        prefs.edit().putBoolean(KEY_IS_TEST_MODE, value).apply()
    }

    init {
        bootstrap()
    }

    private fun bootstrap() {
        val token = app.tokenStore.accessToken
        _phase.value = if (token.isNullOrBlank()) Phase.SignedOut
        else Phase.SignedIn(AuthSession(accessToken = token))
        if (!token.isNullOrBlank()) refreshCurrentUser()
    }

    fun signIn(authService: AuthService) {
        if (_isAuthenticating.value) return
        _isAuthenticating.value = true
        _loginError.value = null
        viewModelScope.launch {
            try {
                val session = authService.signIn()
                app.tokenStore.accessToken = session.accessToken
                setTestMode(false)
                _phase.value = Phase.SignedIn(session)
                refreshCurrentUser()
            } catch (cancel: AuthError.UserCancelled) {
                // Quiet — user explicitly backed out.
            } catch (err: AuthError) {
                _loginError.value = err
            } catch (t: Throwable) {
                _loginError.value = AuthError.Transport(t.localizedMessage ?: "登录失败")
            } finally {
                _isAuthenticating.value = false
            }
        }
    }

    /** 暂不登录 (test environment only): sign in as the seeded test user against the test backend. */
    fun skipLogin() {
        if (_isAuthenticating.value) return
        _isAuthenticating.value = true
        _loginError.value = null
        viewModelScope.launch {
            try {
                val token = app.authApi.testLogin("测试用户", "0010759")
                app.tokenStore.accessToken = token
                setTestMode(true)
                _phase.value = Phase.SignedIn(AuthSession(accessToken = token))
                refreshCurrentUser()
            } catch (err: AuthError) {
                _loginError.value = err
            } catch (t: Throwable) {
                _loginError.value = AuthError.Transport(t.localizedMessage ?: "登录失败")
            } finally {
                _isAuthenticating.value = false
            }
        }
    }

    fun signOut() {
        val current = _phase.value as? Phase.SignedIn
        if (current != null) {
            viewModelScope.launch {
                runCatching { (app.tokenStore.accessToken)?.let { app.userApi /* placeholder */ } }
            }
        }
        app.tokenStore.clear()
        setTestMode(false)
        _currentUser.value = null
        _profileError.value = null
        _phase.value = Phase.SignedOut
    }

    fun refreshCurrentUser() {
        val token = (_phase.value as? Phase.SignedIn)?.session?.accessToken ?: return
        _isLoadingProfile.value = true
        _profileError.value = null
        viewModelScope.launch {
            try {
                _currentUser.value = app.userApi.current(token)
            } catch (err: AuthError) {
                if (err is AuthError.Unauthorized) {
                    // Token expired — drop to signed-out.
                    app.tokenStore.clear()
                    _phase.value = Phase.SignedOut
                } else {
                    _profileError.value = err.errorDescription
                }
            } catch (t: Throwable) {
                _profileError.value = t.localizedMessage ?: "加载失败"
            } finally {
                _isLoadingProfile.value = false
            }
        }
    }

    fun dismissLoginError() {
        _loginError.value = null
    }

    private companion object {
        const val PREFS_NAME = "mentorai_app_state"
        // Matches the iOS UserDefaults key so the semantics are documented identically.
        const val KEY_IS_TEST_MODE = "com.mentorai.app.isTestMode"
    }
}

class AppStateFactory(private val app: MentorAIApp) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T = AppState(app) as T
}
