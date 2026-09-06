package com.mentorai.app.views

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.mentorai.app.ui.charts.TeachTimelineView
import com.mentorai.app.videoanalysis.TeachSegment
import com.mentorai.app.videoanalysis.TeachSummarySection

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TeachSummaryFullScreen(sections: List<TeachSummarySection>, onClose: () -> Unit) {
    var query by remember { mutableStateOf("") }
    val trimmed = query.trim()
    val filtered: List<TeachSummarySection> = remember(trimmed, sections) {
        if (trimmed.isEmpty()) sections else filterSections(sections, trimmed)
    }

    Scaffold(
        topBar = {
            CenterAlignedTopAppBar(
                title = { Text("教学环节总结") },
                navigationIcon = {
                    IconButton(onClick = onClose) {
                        Icon(Icons.Filled.ArrowBack, contentDescription = null)
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier.padding(padding).fillMaxSize().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            SearchField(query = query, onChange = { query = it }, placeholder = "搜索教学环节")
            if (filtered.isEmpty()) {
                Text(
                    "未找到匹配内容",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } else {
                Column(
                    modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    TeachTimelineView(sections = filtered, highlight = trimmed)
                }
            }
        }
    }
}

private fun filterSections(sections: List<TeachSummarySection>, query: String): List<TeachSummarySection> {
    val result = mutableListOf<TeachSummarySection>()
    for (section in sections) {
        val segments: List<TeachSegment> = section.segments.filter {
            it.type.contains(query, ignoreCase = true) ||
                it.content.contains(query, ignoreCase = true) ||
                it.keypoint.contains(query, ignoreCase = true)
        }
        val summaryHit = section.summary.contains(query, ignoreCase = true)
        if (segments.isNotEmpty() || summaryHit) {
            result.add(
                TeachSummarySection(
                    summary = if (summaryHit) section.summary else "",
                    segments = segments.ifEmpty { section.segments },
                )
            )
        }
    }
    return result
}

@Composable
private fun SearchField(query: String, onChange: (String) -> Unit, placeholder: String) {
    OutlinedTextField(
        value = query,
        onValueChange = onChange,
        placeholder = { Text(placeholder) },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )
}
