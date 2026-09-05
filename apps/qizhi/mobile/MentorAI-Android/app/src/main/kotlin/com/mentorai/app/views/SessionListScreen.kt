package com.mentorai.app.views

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChatBubble
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.mentorai.app.MentorAIApp
import com.mentorai.app.R
import com.mentorai.app.app.AppState
import com.mentorai.app.authentication.AuthSession
import com.mentorai.app.chat.ChatSession
import com.mentorai.app.chat.SessionListViewModel
import com.mentorai.app.support.ServerDate
import kotlinx.coroutines.launch

/**
 * Sessions list + in-tab navigation to ChatScreen. Mirrors iOS `SessionListView`.
 * State machine: list ↔ chat (new) ↔ chat (existing-by-id).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SessionListScreen(appState: AppState, session: AuthSession, app: MentorAIApp) {
    val vm = remember {
        SessionListViewModel(
            sessionApi = app.sessionApi,
            tokenProvider = { (appState.phase.value as? AppState.Phase.SignedIn)?.session?.accessToken },
        )
    }
    val sessions by vm.sessions.collectAsState()
    val isLoading by vm.isLoading.collectAsState()
    val error by vm.error.collectAsState()

    var route: ChatRoute? by rememberSaveable(stateSaver = ChatRouteSaver) { mutableStateOf(null) }
    var pendingDelete by remember { mutableStateOf<ChatSession?>(null) }

    LaunchedEffect(Unit) { if (sessions.isEmpty()) vm.refresh() }

    if (route != null) {
        ChatScreen(
            app = app,
            appState = appState,
            initialSessionId = (route as? ChatRoute.Existing)?.id,
            onClose = {
                route = null
                vm.refresh()
            },
        )
        return
    }

    Scaffold(
        // Avoid a second bottom inset on top of MainScreen's nav-bar reservation (the page↔tab-bar gap).
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        topBar = {
            CenterAlignedTopAppBar(
                title = { Text(stringResource(R.string.tab_chat)) },
                actions = {
                    IconButton(onClick = { route = ChatRoute.New }) {
                        Icon(Icons.Filled.Edit, contentDescription = stringResource(R.string.chat_empty_new))
                    }
                },
            )
        },
    ) { padding ->
        Box(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize(),
        ) {
            when {
                error != null && sessions.isEmpty() -> ErrorState(error!!) { vm.refresh() }
                sessions.isEmpty() && !isLoading -> EmptyState(onNew = { route = ChatRoute.New })
                else -> SessionList(
                    sessions = sessions,
                    onOpen = { route = ChatRoute.Existing(it.id) },
                    onRequestDelete = { pendingDelete = it },
                )
            }
        }
    }

    if (pendingDelete != null) {
        val s = pendingDelete!!
        AlertDialog(
            onDismissRequest = { pendingDelete = null },
            confirmButton = {
                TextButton(onClick = {
                    val id = s.id
                    pendingDelete = null
                    vm.delete(id)
                }) {
                    Text(
                        stringResource(R.string.chat_common_delete),
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            },
            dismissButton = {
                TextButton(onClick = { pendingDelete = null }) {
                    Text(stringResource(R.string.common_cancel))
                }
            },
            title = {
                val title = s.displayTitle
                Text(
                    if (title.isNotBlank()) stringResource(R.string.chat_session_delete_title_named, title)
                    else stringResource(R.string.chat_session_delete_title_generic),
                )
            },
            text = { Text(stringResource(R.string.chat_session_delete_confirm)) },
        )
    }
}

sealed class ChatRoute {
    object New : ChatRoute()
    data class Existing(val id: String) : ChatRoute()
}

/** Saveable bridge so the in-tab nav state survives recomposition / config changes. */
private val ChatRouteSaver = androidx.compose.runtime.saveable.Saver<ChatRoute?, String>(
    save = { route ->
        when (route) {
            null -> ""
            ChatRoute.New -> "new"
            is ChatRoute.Existing -> "existing:${route.id}"
        }
    },
    restore = { token ->
        when {
            token.isEmpty() -> null
            token == "new" -> ChatRoute.New
            token.startsWith("existing:") -> ChatRoute.Existing(token.removePrefix("existing:"))
            else -> null
        }
    },
)

@Composable
private fun SessionList(
    sessions: List<ChatSession>,
    onOpen: (ChatSession) -> Unit,
    onRequestDelete: (ChatSession) -> Unit,
) {
    LazyColumn(modifier = Modifier.fillMaxSize()) {
        items(items = sessions, key = { it.id.ifEmpty { it.sortKey } }) { session ->
            SessionRow(
                session = session,
                onOpen = { onOpen(session) },
                onRequestDelete = { onRequestDelete(session) },
            )
            HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SessionRow(
    session: ChatSession,
    onOpen: () -> Unit,
    onRequestDelete: () -> Unit,
) {
    val dismissState = rememberSwipeToDismissBoxState(
        confirmValueChange = { value ->
            if (value == SwipeToDismissBoxValue.EndToStart) {
                onRequestDelete()
                false
            } else false
        },
    )
    SwipeToDismissBox(
        state = dismissState,
        enableDismissFromStartToEnd = false,
        backgroundContent = {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(MaterialTheme.colorScheme.error)
                    .padding(horizontal = 24.dp),
                contentAlignment = Alignment.CenterEnd,
            ) {
                Icon(
                    Icons.Filled.Delete,
                    contentDescription = stringResource(R.string.chat_common_delete),
                    tint = Color.White,
                )
            }
        },
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.surface)
                .clickable { onOpen() }
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.Top,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Box(
                modifier = Modifier
                    .size(44.dp)
                    .background(
                        MaterialTheme.colorScheme.primary.copy(alpha = 0.12f),
                        RoundedCornerShape(10.dp),
                    ),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    Icons.Filled.ChatBubble,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                )
            }
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Text(
                    text = session.displayTitle,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                )
                Text(
                    text = ServerDate.relative(session.sortKey),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
                )
            }
        }
    }
}

@Composable
private fun EmptyState(onNew: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(
            Icons.Filled.ChatBubble,
            contentDescription = null,
            modifier = Modifier.size(56.dp),
            tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f),
        )
        androidx.compose.foundation.layout.Spacer(modifier = Modifier.size(16.dp))
        Text(stringResource(R.string.chat_empty_title), style = MaterialTheme.typography.titleMedium)
        androidx.compose.foundation.layout.Spacer(modifier = Modifier.size(8.dp))
        Text(
            stringResource(R.string.chat_empty_subtitle),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        androidx.compose.foundation.layout.Spacer(modifier = Modifier.size(16.dp))
        Button(onClick = onNew) {
            Icon(Icons.Filled.Edit, contentDescription = null)
            androidx.compose.foundation.layout.Spacer(modifier = Modifier.size(8.dp))
            Text(stringResource(R.string.chat_empty_new), color = Color.White)
        }
    }
}

@Composable
private fun ErrorState(message: String, onRetry: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(
            Icons.Filled.Warning,
            contentDescription = null,
            modifier = Modifier.size(44.dp),
            tint = MaterialTheme.colorScheme.error,
        )
        androidx.compose.foundation.layout.Spacer(modifier = Modifier.size(12.dp))
        Text(stringResource(R.string.chat_list_error_title), style = MaterialTheme.typography.titleMedium)
        androidx.compose.foundation.layout.Spacer(modifier = Modifier.size(8.dp))
        Text(
            message,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        androidx.compose.foundation.layout.Spacer(modifier = Modifier.size(16.dp))
        Button(onClick = onRetry) {
            Text(stringResource(R.string.common_retry), color = Color.White)
        }
    }
}
