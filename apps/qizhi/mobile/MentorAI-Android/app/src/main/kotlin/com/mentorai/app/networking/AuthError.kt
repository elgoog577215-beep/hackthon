package com.mentorai.app.networking

/**
 * One typed error per failure mode, mirroring the iOS `AuthError` enum. Surface these to the
 * user via `errorDescription` so they get localized Chinese text instead of stack-trace gibberish.
 */
sealed class AuthError(message: String) : Exception(message) {

    val errorDescription: String? get() = message

    object UserCancelled : AuthError("已取消登录")
    object InvalidAuthURL : AuthError("登录链接无效")
    object MissingAuthorizationCode : AuthError("未获取到授权码")
    object Unauthorized : AuthError("登录已失效，请重新登录")

    class Transport(detail: String) : AuthError(detail)
    class Server(val status: Int, detail: String?) : AuthError(
        detail?.takeIf { it.isNotBlank() } ?: "服务器错误 (${status})"
    )
}
