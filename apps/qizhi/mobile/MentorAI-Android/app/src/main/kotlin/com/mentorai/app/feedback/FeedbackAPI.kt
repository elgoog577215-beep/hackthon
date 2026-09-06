package com.mentorai.app.feedback

import com.mentorai.app.networking.APIClient
import com.mentorai.app.networking.APIEnvelope
import com.mentorai.app.networking.AuthError
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

/**
 * Wraps the backend `/feedback` POST endpoint. Mirrors `client/website/src/api/feedback.ts` —
 * submits star + content + optional `image_paths`, returns the new feedback id.
 *
 * The server returns the id in `data` on success; we tolerate a null `data` (forward-compat
 * with a future server that drops the field) by returning an empty string instead of throwing.
 */
class FeedbackAPI(private val client: APIClient) {

    suspend fun submit(request: SubmitFeedbackRequest, token: String): String {
        val payload = client.json.encodeToString(SubmitFeedbackRequest.serializer(), request)
        val httpRequest = client.buildRequest(
            method = "POST",
            path = "/feedback",
            body = client.jsonBody(payload),
            bearerToken = token,
        )
        val body = client.executeString(httpRequest)
        val envelope: APIEnvelope<String> = client.json.decodeFromString(
            APIEnvelope.serializer(String.serializer()),
            body,
        )
        if (!envelope.isSuccess) {
            throw AuthError.Server(envelope.code ?: 0, envelope.errorMessage)
        }
        return envelope.data.orEmpty()
    }
}
