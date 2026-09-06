package com.mentorai.app.views

import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AttachFile
import androidx.compose.material.icons.filled.Cancel
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material.icons.outlined.StarOutline
import androidx.compose.material3.Button
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mentorai.app.MentorAIApp
import com.mentorai.app.R
import com.mentorai.app.app.AppState
import com.mentorai.app.feedback.FEEDBACK_MAX_ATTACHMENTS
import com.mentorai.app.feedback.FeedbackAttachment
import com.mentorai.app.feedback.FeedbackViewModel
import kotlinx.coroutines.delay
import java.util.UUID

/**
 * 用户评价与反馈 — Android port of iOS `FeedbackView`. Reached from the Profile tab.
 * Star rating + content + optional attachments → POST /feedback.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FeedbackScreen(
    app: MentorAIApp,
    appState: AppState,
    onClose: () -> Unit,
) {
    val context = LocalContext.current
    val vm = remember {
        FeedbackViewModel(
            feedbackApi = app.feedbackApi,
            attachmentApi = app.attachmentApi,
            tokenProvider = { (appState.phase.value as? AppState.Phase.SignedIn)?.session?.accessToken },
        )
    }

    val star by vm.star.collectAsState()
    val content by vm.content.collectAsState()
    val attachments by vm.attachments.collectAsState()
    val isSubmitting by vm.isSubmitting.collectAsState()
    val submitMessage by vm.submitMessage.collectAsState()
    val submitIsError by vm.submitIsError.collectAsState()
    val starError by vm.starError.collectAsState()
    val contentError by vm.contentError.collectAsState()
    val attachmentError by vm.attachmentError.collectAsState()
    val didSucceed by vm.didSucceed.collectAsState()

    val pickFile = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenMultipleDocuments(),
    ) { uris ->
        for (uri in uris.orEmpty()) {
            var name = uri.lastPathSegment ?: "upload"
            var size = 0L
            context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) {
                    val nameIdx = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    if (nameIdx >= 0) name = cursor.getString(nameIdx) ?: name
                    val sizeIdx = cursor.getColumnIndex(OpenableColumns.SIZE)
                    if (sizeIdx >= 0) size = runCatching { cursor.getLong(sizeIdx) }.getOrDefault(0L)
                }
            }
            vm.addAttachment(context, uri, name, size)
        }
    }

    // Mirror iOS: brief success flash then auto-dismiss.
    LaunchedEffect(didSucceed) {
        if (didSucceed) {
            delay(800)
            onClose()
        }
    }

    Scaffold(
        topBar = {
            CenterAlignedTopAppBar(
                title = { Text(stringRes(R.string.feedback_title)) },
                navigationIcon = {
                    IconButton(onClick = onClose, enabled = !isSubmitting) {
                        Icon(
                            Icons.Filled.Close,
                            contentDescription = stringRes(R.string.feedback_close),
                        )
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .imePadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            RatingCard(
                star = star,
                error = starError,
                onChange = vm::setStar,
            )
            ContentCard(
                content = content,
                error = contentError,
                enabled = !isSubmitting,
                onChange = vm::setContent,
            )
            AttachmentCard(
                attachments = attachments,
                error = attachmentError,
                enabled = !isSubmitting,
                onAdd = {
                    pickFile.launch(arrayOf(
                        "image/*",
                        "video/*",
                        "audio/*",
                        "application/pdf",
                        "text/*",
                        "application/msword",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "application/vnd.ms-powerpoint",
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        "application/vnd.ms-excel",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ))
                },
                onRemove = vm::removeAttachment,
            )
            SubmitCard(
                isSubmitting = isSubmitting,
                canSubmit = vm.canSubmit,
                message = submitMessage,
                isError = submitIsError,
                onSubmit = vm::submit,
            )
            Spacer(modifier = Modifier.height(8.dp))
        }
    }
}

// MARK: - Sections

@Composable
private fun RatingCard(star: Int, error: String?, onChange: (Int) -> Unit) {
    SectionCard(title = stringRes(R.string.feedback_section_rating)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceEvenly,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            for (n in 1..5) {
                val filled = n <= star
                Box(
                    modifier = Modifier
                        .size(44.dp)
                        .clickable { onChange(n) },
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        imageVector = if (filled) Icons.Filled.Star else Icons.Outlined.StarOutline,
                        contentDescription = "$n 星",
                        tint = if (filled) MaterialTheme.colorScheme.primary
                        else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.45f),
                        modifier = Modifier.size(34.dp),
                    )
                }
            }
        }
        if (error != null) ErrorFootnote(error)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ContentCard(
    content: String,
    error: String?,
    enabled: Boolean,
    onChange: (String) -> Unit,
) {
    SectionCard(title = stringRes(R.string.feedback_section_content)) {
        OutlinedTextField(
            value = content,
            onValueChange = onChange,
            enabled = enabled,
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 140.dp),
            placeholder = {
                Text(
                    stringRes(R.string.feedback_content_placeholder),
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
                )
            },
            shape = RoundedCornerShape(10.dp),
            colors = TextFieldDefaults.colors(
                focusedContainerColor = MaterialTheme.colorScheme.surface,
                unfocusedContainerColor = MaterialTheme.colorScheme.surface,
            ),
        )
        if (error != null) ErrorFootnote(error)
    }
}

@Composable
private fun AttachmentCard(
    attachments: List<FeedbackAttachment>,
    error: String?,
    enabled: Boolean,
    onAdd: () -> Unit,
    onRemove: (UUID) -> Unit,
) {
    SectionCard(title = stringRes(R.string.feedback_section_attachments_optional)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                stringRes(R.string.feedback_attachment_max_hint, FEEDBACK_MAX_ATTACHMENTS),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(modifier = Modifier.weight(1f))
            Text(
                text = "${attachments.size} / $FEEDBACK_MAX_ATTACHMENTS",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Spacer(modifier = Modifier.height(8.dp))
        Button(
            onClick = onAdd,
            enabled = enabled && attachments.size < FEEDBACK_MAX_ATTACHMENTS,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Icon(Icons.Filled.AttachFile, contentDescription = null)
            Spacer(modifier = Modifier.width(8.dp))
            Text(stringRes(R.string.feedback_pick_attachments))
        }
        if (attachments.isNotEmpty()) {
            Spacer(modifier = Modifier.height(8.dp))
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for (attachment in attachments) {
                    AttachmentRow(attachment = attachment, onRemove = { onRemove(attachment.id) })
                }
            }
        }
        if (error != null) ErrorFootnote(error)
    }
}

@Composable
private fun SubmitCard(
    isSubmitting: Boolean,
    canSubmit: Boolean,
    message: String?,
    isError: Boolean,
    onSubmit: () -> Unit,
) {
    SectionCard(title = null) {
        Button(
            onClick = onSubmit,
            enabled = canSubmit,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (isSubmitting) {
                CircularProgressIndicator(
                    color = Color.White,
                    strokeWidth = 2.dp,
                    modifier = Modifier.size(16.dp),
                )
                Spacer(modifier = Modifier.width(8.dp))
            }
            Text(
                text = if (isSubmitting) stringRes(R.string.feedback_submitting)
                else stringRes(R.string.feedback_submit),
                color = Color.White,
                fontWeight = FontWeight.SemiBold,
            )
        }
        if (message != null) {
            Spacer(modifier = Modifier.height(10.dp))
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Icon(
                    imageVector = if (isError) Icons.Filled.Warning else Icons.Filled.CheckCircle,
                    contentDescription = null,
                    tint = if (isError) MaterialTheme.colorScheme.error
                    else MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(16.dp),
                )
                Text(
                    text = message,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (isError) MaterialTheme.colorScheme.error
                    else MaterialTheme.colorScheme.primary,
                )
            }
        }
    }
}

@Composable
private fun AttachmentRow(attachment: FeedbackAttachment, onRemove: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.4f), RoundedCornerShape(8.dp))
            .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(8.dp))
            .padding(horizontal = 10.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Icon(
            Icons.Filled.AttachFile,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier.size(20.dp),
        )
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = attachment.filename,
                style = MaterialTheme.typography.bodyMedium,
                maxLines = 1,
            )
            val (statusText, statusColor) = when (val s = attachment.status) {
                is FeedbackAttachment.Status.Uploading -> stringRes(R.string.chat_uploading) to MaterialTheme.colorScheme.onSurfaceVariant
                is FeedbackAttachment.Status.Done -> attachment.displaySize to MaterialTheme.colorScheme.onSurfaceVariant
                is FeedbackAttachment.Status.Error -> s.message to MaterialTheme.colorScheme.error
            }
            Text(
                text = statusText,
                style = MaterialTheme.typography.labelSmall,
                color = statusColor,
                maxLines = 1,
            )
        }
        IconButton(onClick = onRemove, modifier = Modifier.size(28.dp)) {
            Icon(
                Icons.Filled.Cancel,
                contentDescription = stringRes(R.string.feedback_remove_attachment),
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.size(18.dp),
            )
        }
    }
}

// MARK: - Reusable bits

@Composable
private fun SectionCard(title: String?, content: @Composable () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(12.dp))
            .padding(horizontal = 14.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        if (title != null) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontWeight = FontWeight.SemiBold,
            )
            HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
        }
        content()
    }
}

@Composable
private fun ErrorFootnote(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.error,
        fontSize = 12.sp,
    )
}

@Composable
private fun stringRes(id: Int): String = androidx.compose.ui.res.stringResource(id)

@Composable
private fun stringRes(id: Int, vararg args: Any): String =
    androidx.compose.ui.res.stringResource(id, *args)
