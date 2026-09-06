package com.mentorai.app.authentication

import com.mentorai.app.networking.APIClient
import com.mentorai.app.networking.APIEnvelope
import com.mentorai.app.networking.AuthError
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * Two endpoints back the OAuth flow (mirrors `edu_ai_home-dev` server `/auth` routes):
 *  - GET  /auth/url        → returns the ZJU authorization URL (may be a bare string or wrapped).
 *  - GET  /auth/callback   → exchanges the OAuth code for a JWT.
 *  - POST /auth/logout     → invalidates the token (best-effort).
 */
class AuthAPI(private val client: APIClient) {

    /** Resolve the authorize URL the WebView should load. The backend may return the URL as a
     *  string in `data` or as an object with `redirect_url` / `url`. */
    suspend fun authorizationUrl(): String {
        val request = client.buildRequest("GET", "/auth/url")
        val body = client.executeString(request)
        val root = client.json.parseToJsonElement(body)
        val obj = (root as? JsonObject) ?: throw AuthError.Transport("授权地址返回非 JSON")
        if (obj["success"]?.jsonPrimitiveOrNull()?.contentOrNull == "false") {
            throw AuthError.Server(0, obj["error"]?.jsonPrimitiveOrNull()?.contentOrNull)
        }
        val data = obj["data"] ?: return obj.findString(URL_KEYS)
            ?: throw AuthError.InvalidAuthURL
        when (data) {
            is JsonPrimitive -> data.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }?.let { return it }
            is JsonObject -> data.findString(URL_KEYS)?.let { return it }
            else -> Unit
        }
        throw AuthError.InvalidAuthURL
    }

    /** Exchange the OAuth `code` for a JWT. */
    suspend fun exchange(code: String): String {
        val token: String = client.getEnvelope("/auth/callback", mapOf("code" to code))
        if (token.isBlank()) throw AuthError.MissingAuthorizationCode
        return token
    }

    /** Test-environment shortcut (暂不登录): sign in as the seeded test user via
     *  `POST /auth/test-login?name=&zju_id=`. Returns the JWT. Mirrors iOS `AuthAPI.testLogin`. */
    suspend fun testLogin(name: String, zjuId: String): String {
        // OkHttp requires every POST to carry a body; the endpoint only reads query params,
        // so an empty JSON body is enough (matches `logout`).
        val request = client.buildRequest(
            "POST",
            "/auth/test-login",
            mapOf("name" to name, "zju_id" to zjuId),
            body = client.jsonBody("{}"),
        )
        val token: String = client.decodeEnvelope(request)
        if (token.isBlank()) throw AuthError.MissingAuthorizationCode
        return token
    }

    /** Best-effort logout. Failures (e.g. expired token) are swallowed by the caller. */
    suspend fun logout(token: String) {
        val req = client.buildRequest("POST", "/auth/logout", bearerToken = token, body = client.jsonBody("{}"))
        runCatching { client.executeString(req) }
    }

    private fun JsonElement.jsonPrimitiveOrNull(): JsonPrimitive? = this as? JsonPrimitive

    private fun JsonObject.findString(keys: List<String>): String? {
        for (k in keys) {
            val v = this[k] as? JsonPrimitive ?: continue
            val s = v.contentOrNull?.trim()
            if (!s.isNullOrBlank()) return s
        }
        return null
    }

    private companion object {
        val URL_KEYS = listOf("redirect_url", "url", "authorize_url", "authorizeUrl")
    }
}
