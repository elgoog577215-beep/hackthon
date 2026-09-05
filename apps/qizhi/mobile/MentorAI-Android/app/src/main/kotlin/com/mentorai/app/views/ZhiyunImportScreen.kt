package com.mentorai.app.views

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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mentorai.app.MentorAIApp
import com.mentorai.app.R
import com.mentorai.app.app.AppState
import com.mentorai.app.videoanalysis.ZhiyunCourse
import com.mentorai.app.videoanalysis.ZhiyunImportViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ZhiyunImportScreen(
    appState: AppState,
    app: MentorAIApp,
    // Hand the chosen course + a per-import id up to the (persistent) list, which runs the import so
    // it survives this screen closing; progress then shows on the list, not here.
    onImport: (ZhiyunCourse, String) -> Unit,
    onClose: () -> Unit,
) {
    val vm = remember {
        ZhiyunImportViewModel(
            api = app.videoApi,
            tokenProvider = { (appState.phase.value as? AppState.Phase.SignedIn)?.session?.accessToken },
        )
    }
    val phase by vm.phase.collectAsState()
    val beginDate by vm.beginDate.collectAsState()
    val endDate by vm.endDate.collectAsState()
    val courseFilter by vm.courseNameFilter.collectAsState()

    var pendingImport: ZhiyunCourse? by remember { mutableStateOf(null) }
    // Only a course search blocks 返回; the import is owned by the list now, so picking a course
    // hands off and closes this screen — there's no in-screen import phase to block on.
    val isBusy = phase is ZhiyunImportViewModel.Phase.Searching

    Scaffold(
        topBar = {
            CenterAlignedTopAppBar(
                title = { Text(stringResource(R.string.zhiyun_title)) },
                navigationIcon = {
                    if (!isBusy) {
                        TextButton(onClick = onClose) {
                            Text(stringResource(R.string.back_label))
                        }
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
            Section(title = stringResource(R.string.zhiyun_filter_section)) {
                DateRow(label = stringResource(R.string.zhiyun_begin_date), date = beginDate, onPick = vm::setBeginDate)
                HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
                DateRow(label = stringResource(R.string.zhiyun_end_date), date = endDate, onPick = vm::setEndDate)
                HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
                FilterTextField(value = courseFilter, onChange = vm::setCourseNameFilter)
            }

            Button(
                onClick = { vm.searchCourses() },
                enabled = !isBusy,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(),
            ) {
                Icon(Icons.Filled.Search, contentDescription = null, tint = Color.White)
                Spacer(modifier = Modifier.size(8.dp))
                Text(stringResource(R.string.zhiyun_search), color = Color.White)
            }

            PhaseContent(
                phase = phase,
                onPick = { pendingImport = it },
            )
        }
    }

    pendingImport?.let { course ->
        AlertDialog(
            onDismissRequest = { pendingImport = null },
            confirmButton = {
                TextButton(onClick = {
                    val target = course
                    pendingImport = null
                    // Hand off to the list and close this screen — the import keeps running there.
                    onImport(target, UUID.randomUUID().toString())
                }) { Text(stringResource(R.string.zhiyun_import_button), color = MaterialTheme.colorScheme.primary) }
            },
            dismissButton = {
                TextButton(onClick = { pendingImport = null }) { Text(stringResource(R.string.common_cancel)) }
            },
            title = { Text(stringResource(R.string.zhiyun_import_confirm_title_named, course.courseName)) },
            text = {
                Text(
                    stringResource(
                        R.string.zhiyun_import_confirm_message,
                        course.subTitle.ifBlank { course.classBegin },
                    )
                )
            },
        )
    }
}

@Composable
private fun PhaseContent(
    phase: ZhiyunImportViewModel.Phase,
    onPick: (ZhiyunCourse) -> Unit,
) {
    when (phase) {
        ZhiyunImportViewModel.Phase.Idle -> Unit
        ZhiyunImportViewModel.Phase.Searching -> {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(10.dp))
                    .padding(16.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                Text(stringResource(R.string.zhiyun_searching), color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        is ZhiyunImportViewModel.Phase.Picking -> {
            if (phase.courses.isEmpty()) {
                Section(title = "") {
                    Text(
                        stringResource(R.string.zhiyun_no_results),
                        modifier = Modifier.padding(16.dp),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            } else {
                val grouped = remember(phase.courses) { groupByName(phase.courses) }
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(12.dp))
                        .padding(vertical = 8.dp),
                ) {
                    for ((name, sessions) in grouped) {
                        Text(
                            "$name（${sessions.size}）",
                            modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        for (session in sessions) {
                            CourseRow(course = session, onClick = { onPick(session) })
                            HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
                        }
                    }
                }
            }
        }
        // Import is owned by the list now — picking a course hands off and closes this screen, so
        // these phases never render here.
        is ZhiyunImportViewModel.Phase.Importing -> Unit
        is ZhiyunImportViewModel.Phase.Done -> Unit
        is ZhiyunImportViewModel.Phase.Failed -> InlineError(phase.message)
    }
}

@Composable
private fun CourseRow(course: ZhiyunCourse, onClick: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() }
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(
            text = course.subTitle.ifBlank { course.classBegin },
            style = MaterialTheme.typography.bodyMedium,
            maxLines = 2,
        )
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (course.teacherName.isNotBlank()) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Icon(Icons.Filled.Person, contentDescription = null, modifier = Modifier.size(12.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(course.teacherName, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            if (course.classBegin.isNotBlank()) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Icon(Icons.Filled.CalendarMonth, contentDescription = null, modifier = Modifier.size(12.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(course.classBegin, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DateRow(label: String, date: Date, onPick: (Date) -> Unit) {
    var showPicker by remember { mutableStateOf(false) }
    val display = remember(date) {
        SimpleDateFormat("yyyy-MM-dd", Locale.US).format(date)
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { showPicker = true }
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.bodyMedium)
        Spacer(modifier = Modifier.weight(1f))
        Text(
            display,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.primary,
        )
    }
    if (showPicker) {
        val pickerState = rememberDatePickerState(initialSelectedDateMillis = date.time)
        DatePickerDialog(
            onDismissRequest = { showPicker = false },
            confirmButton = {
                TextButton(onClick = {
                    pickerState.selectedDateMillis?.let { onPick(Date(it)) }
                    showPicker = false
                }) { Text(stringResource(R.string.common_confirm)) }
            },
            dismissButton = {
                TextButton(onClick = { showPicker = false }) { Text(stringResource(R.string.common_cancel)) }
            },
        ) {
            DatePicker(state = pickerState)
        }
    }
}

@Composable
private fun FilterTextField(value: String, onChange: (String) -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 12.dp),
    ) {
        BasicTextField(
            value = value,
            onValueChange = onChange,
            singleLine = true,
            textStyle = TextStyle(color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp),
            modifier = Modifier.fillMaxWidth(),
            decorationBox = { inner ->
                if (value.isEmpty()) {
                    Text(
                        stringResource(R.string.zhiyun_course_filter_hint),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
                inner()
            },
        )
    }
}

@Composable
private fun InlineError(message: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.error.copy(alpha = 0.1f), RoundedCornerShape(10.dp))
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(Icons.Filled.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.error)
        Text(message, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
    }
}

private fun groupByName(courses: List<ZhiyunCourse>): List<Pair<String, List<ZhiyunCourse>>> {
    val order = mutableListOf<String>()
    val buckets = linkedMapOf<String, MutableList<ZhiyunCourse>>()
    for (c in courses) {
        val key = c.courseName.ifBlank { "未命名课程" }
        if (key !in buckets) { buckets[key] = mutableListOf(); order.add(key) }
        buckets[key]!!.add(c)
    }
    return order.map { it to (buckets[it]?.toList().orEmpty()) }
}
