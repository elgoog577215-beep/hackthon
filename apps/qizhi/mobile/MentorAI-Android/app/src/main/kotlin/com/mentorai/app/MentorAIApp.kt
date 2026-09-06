package com.mentorai.app

import android.app.Application
import com.mentorai.app.authentication.AuthAPI
import com.mentorai.app.authentication.AuthConfig
import com.mentorai.app.authentication.TokenStore
import com.mentorai.app.chat.AttachmentAPI
import com.mentorai.app.chat.ChatAPI
import com.mentorai.app.chat.SessionAPI
import com.mentorai.app.feedback.FeedbackAPI
import com.mentorai.app.networking.APIClient
import com.mentorai.app.user.UserAPI
import com.mentorai.app.videoanalysis.VideoAPI

/**
 * Application-scoped wiring — replaces the iOS app-level singletons. Constructed once at process
 * start; views get to it via `LocalContext.current.applicationContext as MentorAIApp`.
 */
class MentorAIApp : Application() {
    val authConfig: AuthConfig = AuthConfig.Default
    val apiClient: APIClient by lazy { APIClient(authConfig.apiBaseUrl) }
    val authApi: AuthAPI by lazy { AuthAPI(apiClient) }
    val userApi: UserAPI by lazy { UserAPI(apiClient) }
    val tokenStore: TokenStore by lazy { TokenStore(this) }

    val sessionApi: SessionAPI by lazy { SessionAPI(apiClient) }
    val chatApi: ChatAPI by lazy { ChatAPI(apiClient) }
    val attachmentApi: AttachmentAPI by lazy { AttachmentAPI(apiClient) }
    val videoApi: VideoAPI by lazy { VideoAPI(apiClient) }
    val feedbackApi: FeedbackAPI by lazy { FeedbackAPI(apiClient) }
}
