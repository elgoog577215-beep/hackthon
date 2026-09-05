package com.mentorai.app.ui

import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.MediaItem
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import com.mentorai.app.authentication.AuthConfig

/**
 * In-app video preview, mirroring the iOS `VideoPreviewPlayer`. Builds an ExoPlayer + wraps a
 * `PlayerView` via AndroidView; releases the player on disposal so we don't leak audio focus.
 *
 * `rawPath` matches the iOS `videoURL(for:)` heuristic — handles full URLs, `/static/...` paths,
 * and the raw `uploads/...` filesystem path the server stores.
 */
@OptIn(UnstableApi::class)
@Composable
fun VideoPlayerView(rawPath: String, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val url = remember(rawPath) { resolveVideoMediaUrl(rawPath) }
    if (url == null) return

    val player = remember(url) {
        ExoPlayer.Builder(context).build().apply {
            setMediaItem(MediaItem.fromUri(url))
            prepare()
            playWhenReady = false
        }
    }
    DisposableEffect(player) { onDispose { player.release() } }

    AndroidView(
        modifier = modifier
            .fillMaxWidth()
            .aspectRatio(16f / 9f)
            .clip(RoundedCornerShape(12.dp)),
        factory = { ctx ->
            PlayerView(ctx).apply {
                this.player = player
                useController = true
            }
        },
    )
}

/**
 * Mirrors iOS `VideoAnalysisDetailView.videoURL(for:)`. The file is always served from the
 * `/static/` mount; also tolerates the malformed paths the local-upload flow can store — e.g.
 * a server-local prefix + doubled slash like `/src//static/videos/…` — by resolving to the
 * `/static/` segment regardless of any junk before it.
 */
private fun resolveVideoMediaUrl(raw: String): String? {
    val trimmed = raw.trim()
    if (trimmed.isEmpty()) return null
    if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) return trimmed
    var path = trimmed
    val staticIdx = path.lastIndexOf("/static/")
    if (staticIdx >= 0) {
        path = path.substring(staticIdx) // drop anything before the static mount
    } else {
        val idx = path.indexOf("uploads/")
        if (idx >= 0) path = "/static/" + path.substring(idx + "uploads/".length)
    }
    if (!path.startsWith("/")) path = "/$path"
    while (path.contains("//")) path = path.replace("//", "/") // collapse doubled slashes
    val base = AuthConfig.Default.apiBaseUrl.trimEnd('/')
    return base + path
}
