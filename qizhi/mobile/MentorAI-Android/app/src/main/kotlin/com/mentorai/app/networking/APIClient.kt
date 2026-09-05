package com.mentorai.app.networking

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.json.Json
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.logging.HttpLoggingInterceptor
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Thin OkHttp wrapper. Each module's API class composes this to issue requests; helpers handle
 * URL building, bearer tokens, and JSON envelope unwrapping. Streaming endpoints (SSE, chunked
 * upload) talk to `httpClient` directly.
 */
class APIClient(
    val baseUrl: String,
    val json: Json = DefaultJson,
    val httpClient: OkHttpClient = defaultHttpClient(),
) {
    companion object {
        val DefaultJson: Json = Json {
            ignoreUnknownKeys = true
            isLenient = true
            coerceInputValues = true
            explicitNulls = false
        }

        fun defaultHttpClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(300, TimeUnit.SECONDS)
            .writeTimeout(300, TimeUnit.SECONDS)
            .addInterceptor(HttpLoggingInterceptor().apply {
                level = HttpLoggingInterceptor.Level.BASIC
            })
            .build()
    }

    fun buildRequest(
        method: String,
        path: String,
        query: Map<String, String?> = emptyMap(),
        body: RequestBody? = null,
        bearerToken: String? = null,
        accept: String = "application/json",
    ): Request {
        val cleanPath = path.removePrefix("/")
        val base = if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/"
        val urlBuilder = (base + cleanPath).toHttpUrl().newBuilder()
        for ((k, v) in query) {
            if (v != null && v.isNotEmpty()) urlBuilder.addQueryParameter(k, v)
        }
        val builder = Request.Builder()
            .url(urlBuilder.build())
            .method(method, body)
            .header("Accept", accept)
        if (!bearerToken.isNullOrBlank()) {
            builder.header("Authorization", "Bearer $bearerToken")
        }
        return builder.build()
    }

    fun jsonBody(payload: String): RequestBody =
        payload.toRequestBody("application/json; charset=utf-8".toMediaType())

    fun formBody(payload: String): RequestBody =
        payload.toRequestBody("application/x-www-form-urlencoded".toMediaType())

    /**
     * Executes `request` and returns the response body as a string. Throws `AuthError.Server` on
     * non-2xx and `AuthError.Transport` on network failure, mirroring the iOS error mapping.
     */
    suspend fun executeString(request: Request): String = suspendCancellableCoroutine { cont ->
        val call = httpClient.newCall(request)
        cont.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                cont.resumeWithException(AuthError.Transport(e.localizedMessage ?: "网络请求失败"))
            }
            override fun onResponse(call: Call, response: Response) {
                response.use { resp ->
                    val text = resp.body?.string().orEmpty()
                    if (!resp.isSuccessful) {
                        val err = if (resp.code == 401) AuthError.Unauthorized
                        else AuthError.Server(resp.code, text.take(500).ifBlank { null })
                        cont.resumeWithException(err)
                        return
                    }
                    cont.resume(text)
                }
            }
        })
    }

    /** Decode a typed envelope from a finished request and unwrap the `data` field. */
    @OptIn(ExperimentalSerializationApi::class)
    suspend inline fun <reified T> getEnvelope(
        path: String,
        query: Map<String, String?> = emptyMap(),
        bearerToken: String? = null,
    ): T = decodeEnvelope(buildRequest("GET", path, query, null, bearerToken))

    suspend inline fun <reified T> postEnvelope(
        path: String,
        jsonString: String,
        bearerToken: String? = null,
    ): T = decodeEnvelope(buildRequest("POST", path, body = jsonBody(jsonString), bearerToken = bearerToken))

    suspend inline fun <reified T> postFormEnvelope(
        path: String,
        form: String,
        bearerToken: String? = null,
    ): T = decodeEnvelope(buildRequest("POST", path, body = formBody(form), bearerToken = bearerToken))

    suspend inline fun deleteEnvelope(
        path: String,
        query: Map<String, String?> = emptyMap(),
        bearerToken: String? = null,
    ) {
        val body = executeString(buildRequest("DELETE", path, query, null, bearerToken))
        val env: APIEnvelope<Unit> = json.decodeFromString(body)
        if (!env.isSuccess) throw AuthError.Server(env.code ?: 0, env.errorMessage)
    }

    suspend inline fun <reified T> decodeEnvelope(request: Request): T = withContext(Dispatchers.IO) {
        val body = executeString(request)
        val envelope: APIEnvelope<T> = json.decodeFromString(body)
        if (!envelope.isSuccess) throw AuthError.Server(envelope.code ?: 0, envelope.errorMessage)
        envelope.data ?: throw AuthError.Server(envelope.code ?: 0, "服务器未返回数据")
    }
}
