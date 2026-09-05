package com.mentorai.app.views

import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.School
import androidx.compose.material.icons.filled.UploadFile
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.mentorai.app.MentorAIApp
import com.mentorai.app.R
import com.mentorai.app.app.AppState
import com.mentorai.app.videoanalysis.ZhiyunCourse

/**
 * Source picker for a fresh video analysis — Zhiyun import or local file upload.
 * Mirrors iOS `NewVideoAnalysisView`.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NewVideoAnalysisScreen(
    appState: AppState,
    app: MentorAIApp,
    // Both flows hand off to the (persistent) list VM, which runs them so they survive this screen
    // closing. `onZhiyunImport` carries the chosen course + a per-import id; `onUpload` carries the
    // picked Uri + display name.
    onZhiyunImport: (ZhiyunCourse, String) -> Unit,
    onUpload: (Uri, String) -> Unit,
    onClose: () -> Unit,
) {
    val context = LocalContext.current
    val testMode by appState.isTestMode.collectAsState()
    var pickedFile: PickedFile? by remember { mutableStateOf(null) }
    var route by remember { mutableStateOf<NewRoute?>(null) }

    val pickLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocument(),
    ) { uri: Uri? ->
        if (uri != null) {
            val (name, size) = queryFileNameAndSize(context.contentResolver, uri)
            pickedFile = PickedFile(uri = uri, name = name, size = size)
            route = NewRoute.Upload
        }
    }

    when (route) {
        NewRoute.Zhiyun -> {
            ZhiyunImportScreen(
                appState = appState,
                app = app,
                onImport = onZhiyunImport,
                onClose = { route = null },
            )
            return
        }
        NewRoute.Upload -> {
            val file = pickedFile
            if (file != null) {
                CustomVideoUploadScreen(
                    fileUri = file.uri,
                    fileName = file.name,
                    onUpload = onUpload,
                    onClose = { route = null; pickedFile = null },
                )
                return
            }
        }
        null -> Unit
    }

    Scaffold(
        topBar = {
            CenterAlignedTopAppBar(
                title = { Text(stringResource(R.string.video_new_title)) },
                navigationIcon = {
                    IconButton(onClick = onClose) {
                        Icon(Icons.Filled.Close, contentDescription = stringResource(R.string.common_cancel))
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Section(title = stringResource(R.string.video_new_source_section)) {
                SourceRow(
                    title = stringResource(R.string.video_new_source_zhiyun_title),
                    // 智云课堂 needs 浙大通行证; in test mode it's disabled (grayed) with a hint.
                    subtitle = if (testMode) {
                        stringResource(R.string.video_new_source_zhiyun_subtitle_testmode)
                    } else {
                        stringResource(R.string.video_new_source_zhiyun_subtitle)
                    },
                    icon = Icons.Filled.School,
                    tint = if (testMode) Color.Gray else MaterialTheme.colorScheme.primary,
                    enabled = !testMode,
                    onClick = { route = NewRoute.Zhiyun },
                )
                HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
                SourceRow(
                    title = stringResource(R.string.video_new_source_local_title),
                    subtitle = stringResource(R.string.video_new_source_local_subtitle),
                    icon = Icons.Filled.UploadFile,
                    onClick = { pickLauncher.launch(arrayOf("video/*")) },
                )
            }
            Text(
                stringResource(R.string.video_new_footer),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 4.dp),
            )
        }
    }
}

private sealed class NewRoute { object Zhiyun : NewRoute(); object Upload : NewRoute() }
private data class PickedFile(val uri: Uri, val name: String, val size: Long)

@Composable
internal fun Section(title: String, content: @Composable () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(12.dp)),
    ) {
        Text(
            title,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        content()
    }
}

@Composable
private fun SourceRow(
    title: String,
    subtitle: String,
    icon: ImageVector,
    onClick: () -> Unit,
    tint: Color = MaterialTheme.colorScheme.primary,
    enabled: Boolean = true,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .then(if (enabled) Modifier.clickable { onClick() } else Modifier)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Icon(
            icon,
            contentDescription = null,
            tint = tint,
            modifier = Modifier.size(32.dp),
        )
        Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.Medium)
            Text(
                subtitle,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Icon(
            Icons.Filled.ChevronRight,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f),
            modifier = Modifier.size(16.dp),
        )
    }
}

internal fun queryFileNameAndSize(resolver: android.content.ContentResolver, uri: Uri): Pair<String, Long> {
    var name = uri.lastPathSegment ?: "upload"
    var size = 0L
    resolver.query(uri, null, null, null, null)?.use { cursor ->
        if (cursor.moveToFirst()) {
            val ni = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (ni >= 0) name = cursor.getString(ni) ?: name
            val si = cursor.getColumnIndex(OpenableColumns.SIZE)
            if (si >= 0) size = runCatching { cursor.getLong(si) }.getOrDefault(0L)
        }
    }
    return name to size
}
