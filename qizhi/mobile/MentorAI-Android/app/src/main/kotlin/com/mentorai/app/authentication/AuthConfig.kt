package com.mentorai.app.authentication

/**
 * Which backend environment this build targets. The test (internal/QA) environment uses the
 * test server and shows the "暂不登录" shortcut; production uses the ZJU server and hides it.
 * Production-only: every build (debug + release) targets Production and hides 暂不登录 (see
 * `current` below). Mirrors the iOS `AppEnvironment`; Android wires one base URL at app
 * construction rather than switching per login action.
 */
enum class AppEnvironment {
    Test,
    Production;

    val config: AuthConfig
        get() = when (this) {
            Test -> AuthConfig.Test
            Production -> AuthConfig.Production
        }

    /** Whether to show the "暂不登录" (skip-login / 模拟登录) button on the login screen. */
    val showsSkipLogin: Boolean get() = this == Test

    companion object {
        // Production-only: every build (debug + release) targets the ZJU production backend and
        // hides 暂不登录, so real users can't accidentally land in the test database.
        // (For local testing against 127.0.0.1, temporarily change this to Test.)
        val current: AppEnvironment = Production
    }
}

/**
 * Backend base URL. The MentorAI/启智 backend runs over http; the network security config
 * whitelists *.zju.edu.cn and the test server IP for cleartext traffic.
 */
data class AuthConfig(
    val apiBaseUrl: String,
) {
    companion object {
        val Production = AuthConfig(apiBaseUrl = "http://jsfzai.zju.edu.cn/api")
        val Test = AuthConfig(apiBaseUrl = "http://127.0.0.1:8000")

        /** The active config for this build's environment. */
        val Default: AuthConfig get() = AppEnvironment.current.config
    }
}
