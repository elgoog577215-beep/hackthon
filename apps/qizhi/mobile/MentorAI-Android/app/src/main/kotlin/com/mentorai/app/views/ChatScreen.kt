package com.mentorai.app.views

import android.app.Activity
import android.content.Intent
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.StartOffset
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.keyframes
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.AttachFile
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.ArrowOutward
import androidx.compose.material.icons.filled.Cancel
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Lightbulb
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.ScaffoldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mentorai.app.MentorAIApp
import com.mentorai.app.R
import com.mentorai.app.app.AppState
import com.mentorai.app.chat.ChatAttachment
import com.mentorai.app.chat.ChatMessage
import com.mentorai.app.chat.ChatRole
import com.mentorai.app.chat.ChatViewModel
import com.mentorai.app.support.decodingJsonEscapes
import com.mentorai.app.support.relaxingCJKBoldFlanking
import com.mentorai.app.ui.LocalBottomBarVisibility
import com.mentorai.app.ui.MarkdownText

private val Suggestions = listOf(
    "帮我设计一节课的教学大纲",
    "围绕一个知识点出 5 道练习题",
    "把一段课文改写得更通俗易懂",
    "总结一份资料的核心要点",
)

/**
 * Chat detail. Mirrors iOS `ChatView` — load history, stream replies, render Markdown for
 * assistant turns, support attachments, surface a welcome + suggestion chips when empty.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(
    app: MentorAIApp,
    appState: AppState,
    initialSessionId: String?,
    onClose: () -> Unit,
) {
    val context = LocalContext.current
    val vm = remember(initialSessionId) {
        ChatViewModel(
            initialSessionId = initialSessionId,
            chatApi = app.chatApi,
            sessionApi = app.sessionApi,
            attachmentApi = app.attachmentApi,
            tokenProvider = {
                (appState.phase.value as? AppState.Phase.SignedIn)?.session?.accessToken
            },
        )
    }

    val messages by vm.messages.collectAsState()
    val draft by vm.draft.collectAsState()
    val statusText by vm.statusText.collectAsState()
    val isStreaming by vm.isStreaming.collectAsState()
    val streamError by vm.streamError.collectAsState()
    val isLoadingSession by vm.isLoadingSession.collectAsState()
    val sessionError by vm.sessionError.collectAsState()
    val attachments by vm.attachments.collectAsState()

    LaunchedEffect(initialSessionId) { vm.load() }

    val showWelcome = messages.isEmpty() && !isLoadingSession && sessionError == null

    // Mirror iOS `.fileImporter(allowsMultipleSelection: true)` — pick any number of files and
    // enqueue each (querying display name + size per uri).
    val pickFile = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenMultipleDocuments(),
    ) { uris ->
        for (uri in uris) {
            val (name, size) = queryFileMeta(context, uri)
            vm.addAttachment(context, uri, name, size)
        }
    }

    // (#27) Hide the parent MainScreen's bottom nav for the lifetime of this screen — restore on
    // back. Mirrors iOS `.toolbar(.hidden, for: .tabBar)`.
    val bottomBarVisibility = LocalBottomBarVisibility.current
    DisposableEffect(Unit) {
        bottomBarVisibility.hidden = true
        onDispose { bottomBarVisibility.hidden = false }
    }

    // (#28) Tap-anywhere-blank to dismiss the keyboard. Detected as a single tap so the gesture
    // doesn't fight the message-stack vertical scroll.
    val focusManager = LocalFocusManager.current
    val keyboardController = LocalSoftwareKeyboardController.current
    val dismissKeyboard: () -> Unit = {
        keyboardController?.hide()
        focusManager.clearFocus()
    }

    Scaffold(
        topBar = {
            // Hand-rolled top bar — both Material 3 `TopAppBar` flavors clamp the title slot
            // to a much smaller intrinsic width than the bar's actual space, so even long
            // session titles were collapsing to "评审..." while half the bar sat empty. A
            // plain `Row` lets the title `Text` take everything left over after the close
            // button (`weight(1f)`), so it ellipsizes only at the real right edge.
            Surface(
                color = MaterialTheme.colorScheme.surface,
                tonalElevation = 0.dp,
                modifier = Modifier
                    .fillMaxWidth()
                    .windowInsetsPadding(WindowInsets.statusBars),
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(56.dp)
                        .padding(end = 16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    IconButton(onClick = onClose) {
                        Icon(
                            Icons.Filled.Close,
                            contentDescription = stringResource(R.string.common_cancel),
                        )
                    }
                    Text(
                        text = vm.titleForDisplay,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        },
        // Don't let Scaffold consume the bottom (nav-bar) inset — the InputBar handles it
        // via navigationBarsPadding() so its background extends into the safe area seamlessly.
        contentWindowInsets = ScaffoldDefaults.contentWindowInsets
            .only(androidx.compose.foundation.layout.WindowInsetsSides.Horizontal +
                  androidx.compose.foundation.layout.WindowInsetsSides.Top),
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                // Lift the input bar above the IME so the keyboard doesn't obscure the field.
                .imePadding(),
        ) {
            Box(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .pointerInput(Unit) {
                        detectTapGestures(onTap = { dismissKeyboard() })
                    },
            ) {
                if (showWelcome) {
                    WelcomeState(
                        onPick = { suggestion ->
                            vm.setDraft(suggestion)
                            vm.send()
                        },
                    )
                } else {
                    MessageStack(
                        messages = messages,
                        isStreaming = isStreaming,
                        isLoadingSession = isLoadingSession,
                        sessionError = sessionError,
                        onRetryLoad = vm::retryLoad,
                        streamError = streamError,
                    )
                }
            }
            StatusOverlay(isStreaming = isStreaming, status = statusText)
            AttachmentTray(attachments = attachments, onRemove = vm::removeAttachment)
            HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
            InputBar(
                draft = draft,
                onDraftChange = vm::setDraft,
                isStreaming = isStreaming,
                canSend = vm.canSend,
                onAttach = { pickFile.launch(arrayOf("*/*")) },
                onSend = { vm.send() },
                onStop = { vm.cancel() },
            )
        }
    }
}

// -------- subviews --------

@Composable
private fun MessageStack(
    messages: List<ChatMessage>,
    isStreaming: Boolean,
    isLoadingSession: Boolean,
    sessionError: String?,
    onRetryLoad: () -> Unit,
    streamError: String?,
) {
    val scroll = rememberScrollState()
    // When messages first arrive (history load) or grow during streaming, follow the bottom of
    // the column. The initial `LaunchedEffect` firing races layout — `scroll.maxValue` may still
    // be 0 (or stale) when this runs, so we additionally observe maxValue and re-snap until it
    // stops growing. Keyed on messages so each new turn restarts the chase.
    LaunchedEffect(messages.size, messages.lastOrNull()?.content) {
        androidx.compose.runtime.snapshotFlow { scroll.maxValue }
            .collect { max ->
                if (max > 0) scroll.scrollTo(max)
            }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(scroll)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        if (isLoadingSession) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Center,
            ) {
                CircularProgressIndicator(modifier = Modifier.size(28.dp), strokeWidth = 2.dp)
            }
        }
        if (sessionError != null) {
            InlineError(text = sessionError, onRetry = onRetryLoad)
        }
        messages.forEachIndexed { index, message ->
            val isTail = isStreaming && index == messages.lastIndex && message.role == ChatRole.Assistant
            MessageBubble(message = message, isStreamingTail = isTail)
        }
        if (streamError != null) {
            InlineError(text = streamError, onRetry = null)
        }
        Spacer(modifier = Modifier.height(1.dp))
    }
}

@Composable
private fun MessageBubble(message: ChatMessage, isStreamingTail: Boolean) {
    when {
        message.role == ChatRole.User -> UserBubble(message)
        message.content.isEmpty() && isStreamingTail -> AssistantBubble(content = null, isTyping = true)
        message.content.isEmpty() -> AssistantBubble(content = "…", isTyping = false)
        else -> {
            // Match iOS `ChatView.content` render order: while streaming, decode JSON escapes at
            // render time (finished/loaded messages are already decoded server-side), then relax
            // CJK + punctuation bold flanking so `**X(青教赛)**的备赛` renders bold instead of
            // emitting literal `**`.
            val decoded = if (isStreamingTail) message.content.decodingJsonEscapes() else message.content
            AssistantBubble(content = decoded.relaxingCJKBoldFlanking(), isTyping = false)
        }
    }
}

@Composable
private fun UserBubble(message: ChatMessage) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.End,
    ) {
        Spacer(modifier = Modifier.width(48.dp))
        Box(
            modifier = Modifier
                .background(MaterialTheme.colorScheme.primary, RoundedCornerShape(18.dp))
                .padding(horizontal = 14.dp, vertical = 9.dp),
        ) {
            // Parity with iOS `.textSelection(.enabled)` on the user bubble (the assistant bubble
            // is already selectable via MarkdownText's selectable TextView).
            SelectionContainer {
                Text(
                    text = message.content,
                    color = Color.White,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
    }
}

@Composable
private fun AssistantBubble(content: String?, isTyping: Boolean) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = if (isTyping) Alignment.CenterVertically else Alignment.Top,
    ) {
        Box(
            modifier = Modifier
                .size(28.dp)
                .background(MaterialTheme.colorScheme.primary, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                Icons.Filled.AutoAwesome,
                contentDescription = null,
                tint = Color.White,
                modifier = Modifier.size(14.dp),
            )
        }
        if (isTyping) {
            TypingIndicator()
        } else if (!content.isNullOrEmpty()) {
            MarkdownText(text = content, modifier = Modifier.weight(1f))
        }
    }
}

/**
 * Animated three-dot typing indicator shown while the assistant's first token is pending.
 * Mirrors iOS `ChatView.TypingIndicator` — three 6dp dots pulsing in a staggered wave (~0.35s
 * per dot) instead of a static "…".
 */
@Composable
private fun TypingIndicator(modifier: Modifier = Modifier) {
    val transition = rememberInfiniteTransition(label = "typing")
    val dotColor = MaterialTheme.colorScheme.onSurface
    Row(
        modifier = modifier.widthIn(min = 30.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        repeat(3) { index ->
            // Each dot pulses once per 1050ms cycle; a 350ms start delay per dot staggers them
            // into a left-to-right wave. End value matches the start so the 700-1050ms tail holds
            // flat instead of ramping back up.
            val progress by transition.animateFloat(
                initialValue = 0.35f,
                targetValue = 0.35f,
                animationSpec = infiniteRepeatable(
                    animation = keyframes {
                        durationMillis = 1050
                        0.35f at 0
                        1f at 350
                        0.35f at 700
                    },
                    repeatMode = RepeatMode.Restart,
                    initialStartOffset = StartOffset(index * 350),
                ),
                label = "dot$index",
            )
            Box(
                modifier = Modifier
                    .size(6.dp)
                    .graphicsLayer {
                        scaleX = progress
                        scaleY = progress
                        alpha = progress
                    }
                    .background(dotColor, CircleShape),
            )
        }
    }
}

@Composable
private fun StatusOverlay(isStreaming: Boolean, status: String?) {
    if (!isStreaming || status.isNullOrEmpty()) return
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(horizontal = 16.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        CircularProgressIndicator(modifier = Modifier.size(14.dp), strokeWidth = 2.dp)
        Text(
            text = status,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun AttachmentTray(attachments: List<ChatAttachment>, onRemove: (java.util.UUID) -> Unit) {
    if (attachments.isEmpty()) return
    val scroll = rememberScrollState()
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .horizontalScroll(scroll)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        for (attachment in attachments) {
            AttachmentChip(attachment = attachment, onRemove = { onRemove(attachment.id) })
        }
    }
}

@Composable
private fun AttachmentChip(attachment: ChatAttachment, onRemove: () -> Unit) {
    val tint = when (attachment.status) {
        is ChatAttachment.Status.Uploading -> MaterialTheme.colorScheme.onSurfaceVariant
        is ChatAttachment.Status.Done -> MaterialTheme.colorScheme.primary
        is ChatAttachment.Status.Error -> MaterialTheme.colorScheme.error
    }
    Row(
        modifier = Modifier
            .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(10.dp))
            .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(10.dp))
            .padding(horizontal = 8.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(Icons.Filled.AttachFile, contentDescription = null, tint = tint, modifier = Modifier.size(16.dp))
        Column(modifier = Modifier.widthIn(max = 180.dp)) {
            Text(
                text = attachment.filename,
                style = MaterialTheme.typography.bodySmall,
                maxLines = 1,
            )
            val subtitle = when (val s = attachment.status) {
                is ChatAttachment.Status.Uploading -> stringResource(R.string.chat_uploading)
                is ChatAttachment.Status.Done -> attachment.displaySize
                is ChatAttachment.Status.Error -> s.message
            }
            Text(
                text = subtitle,
                style = MaterialTheme.typography.labelSmall,
                color = tint,
                maxLines = 1,
            )
        }
        IconButton(onClick = onRemove, modifier = Modifier.size(28.dp)) {
            Icon(
                Icons.Filled.Cancel,
                contentDescription = stringResource(R.string.chat_remove_attachment),
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.size(16.dp),
            )
        }
    }
}

@Composable
private fun InputBar(
    draft: String,
    onDraftChange: (String) -> Unit,
    isStreaming: Boolean,
    canSend: Boolean,
    onAttach: () -> Unit,
    onSend: () -> Unit,
    onStop: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface)
            .navigationBarsPadding()
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        IconButton(onClick = onAttach, enabled = !isStreaming) {
            Icon(
                Icons.Filled.AttachFile,
                contentDescription = stringResource(R.string.chat_attach_label),
                tint = if (isStreaming) MaterialTheme.colorScheme.onSurfaceVariant
                else MaterialTheme.colorScheme.primary,
            )
        }
        Box(
            modifier = Modifier
                .weight(1f)
                .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(18.dp))
                .padding(horizontal = 12.dp, vertical = 8.dp),
        ) {
            BasicTextField(
                value = draft,
                onValueChange = onDraftChange,
                textStyle = TextStyle(color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp),
                enabled = !isStreaming,
                maxLines = 5,
                modifier = Modifier.fillMaxWidth(),
                decorationBox = { inner ->
                    if (draft.isEmpty()) {
                        Text(
                            stringResource(R.string.chat_input_placeholder),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    }
                    inner()
                },
            )
        }
        if (isStreaming) {
            IconButton(onClick = onStop) {
                Icon(
                    Icons.Filled.Stop,
                    contentDescription = stringResource(R.string.chat_stop_label),
                    tint = MaterialTheme.colorScheme.error,
                )
            }
        } else {
            IconButton(onClick = onSend, enabled = canSend) {
                Icon(
                    Icons.Filled.ArrowUpward,
                    contentDescription = stringResource(R.string.chat_send_label),
                    tint = if (canSend) MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun WelcomeState(onPick: (String) -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp, vertical = 56.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(28.dp),
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Box(
                modifier = Modifier
                    .size(64.dp)
                    .background(MaterialTheme.colorScheme.primary, RoundedCornerShape(18.dp)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    Icons.Filled.AutoAwesome,
                    contentDescription = null,
                    tint = Color.White,
                    modifier = Modifier.size(28.dp),
                )
            }
            Text(
                stringResource(R.string.chat_welcome_greeting),
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                stringResource(R.string.chat_welcome_subtitle),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )
        }
        Column(modifier = Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            for (s in Suggestions) {
                SuggestionChip(text = s, onClick = { onPick(s) })
            }
        }
    }
}

@Composable
private fun SuggestionChip(text: String, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(14.dp))
            .clickable { onClick() }
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Icon(Icons.Filled.Lightbulb, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
        Text(
            text = text,
            modifier = Modifier.weight(1f),
            style = MaterialTheme.typography.bodyMedium,
        )
        Icon(
            Icons.Filled.ArrowOutward,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f),
            modifier = Modifier.size(14.dp),
        )
    }
}

@Composable
private fun InlineError(text: String, onRetry: (() -> Unit)?) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.error.copy(alpha = 0.1f), RoundedCornerShape(10.dp))
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Icon(Icons.Filled.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.error)
            Text(text = text, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
        }
        if (onRetry != null) {
            Text(
                text = stringResource(R.string.chat_session_error_retry),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.clickable { onRetry() },
            )
        }
    }
}

// -------- helpers --------

private fun queryFileMeta(context: android.content.Context, uri: android.net.Uri): Pair<String, Long> {
    var name = uri.lastPathSegment ?: "upload"
    var size: Long = 0
    context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
        if (cursor.moveToFirst()) {
            val nameIdx = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (nameIdx >= 0) name = cursor.getString(nameIdx) ?: name
            val sizeIdx = cursor.getColumnIndex(OpenableColumns.SIZE)
            if (sizeIdx >= 0) size = runCatching { cursor.getLong(sizeIdx) }.getOrDefault(0L)
        }
    }
    return name to size
}
