package com.mentorai.app.views

import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.UploadFile
import androidx.compose.material3.Button
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mentorai.app.R

/**
 * 本地视频 prep step — mirrors iOS `CustomVideoUploadView`. PREP-ONLY: it only collects the
 * 文件名 / 视频名称, then on 开始上传 hands the picked Uri + name to the list ViewModel (via
 * [onUpload]) and closes. The actual chunked upload runs in the background, surfaced in the list's
 * task banner. No analysis is started here; the uploaded video lands 未开始分析 and the user picks
 * 云端 / 本地 on its detail page.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CustomVideoUploadScreen(
    fileUri: Uri,
    fileName: String,
    onUpload: (Uri, String) -> Unit,
    onClose: () -> Unit,
) {
    var videoName by remember(fileName) {
        val suggested = fileName.substringBeforeLast('.', fileName).trim()
        mutableStateOf(suggested.ifEmpty { "未命名视频" })
    }
    val canStart = videoName.trim().isNotEmpty()

    Scaffold(
        topBar = {
            CenterAlignedTopAppBar(
                title = { Text(stringResource(R.string.upload_title)) },
                navigationIcon = {
                    TextButton(onClick = onClose) { Text(stringResource(R.string.back_label)) }
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
            Section(title = stringResource(R.string.upload_file_section)) {
                LabeledRow(stringResource(R.string.upload_file_name), fileName)
            }

            Section(title = stringResource(R.string.upload_video_name_section)) {
                Box(modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp)) {
                    BasicTextField(
                        value = videoName,
                        onValueChange = { videoName = it },
                        singleLine = true,
                        textStyle = TextStyle(color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp),
                        modifier = Modifier.fillMaxWidth(),
                        decorationBox = { inner ->
                            if (videoName.isEmpty()) {
                                Text(
                                    stringResource(R.string.upload_video_name_hint),
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    style = MaterialTheme.typography.bodyMedium,
                                )
                            }
                            inner()
                        },
                    )
                }
            }

            Button(
                onClick = {
                    onUpload(fileUri, videoName)
                    onClose()
                },
                enabled = canStart,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Icon(Icons.Filled.UploadFile, contentDescription = null, tint = Color.White)
                Spacer(modifier = Modifier.size(8.dp))
                Text(stringResource(R.string.upload_start), color = Color.White)
            }

            Text(
                stringResource(R.string.upload_footer),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 4.dp),
            )
        }
    }
}

@Composable
private fun LabeledRow(label: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.bodyMedium)
        Spacer(modifier = Modifier.weight(1f))
        Text(value, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
    }
}
