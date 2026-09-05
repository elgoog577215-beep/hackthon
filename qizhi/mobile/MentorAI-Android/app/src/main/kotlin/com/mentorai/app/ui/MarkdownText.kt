package com.mentorai.app.ui

import android.text.method.LinkMovementMethod
import android.view.ViewGroup
import android.widget.TextView
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.res.ResourcesCompat
import com.mentorai.app.R
import io.noties.markwon.AbstractMarkwonPlugin
import io.noties.markwon.Markwon
import io.noties.markwon.core.MarkwonTheme
import io.noties.markwon.ext.strikethrough.StrikethroughPlugin
import io.noties.markwon.ext.tables.TablePlugin
import io.noties.markwon.ext.tasklist.TaskListPlugin
import io.noties.markwon.linkify.LinkifyPlugin

/**
 * TextView-backed Markdown renderer (Markwon) wrapped for Compose. Matches the iOS MarkdownUI
 * setup: headings, lists, tables, strikethrough, task lists, link-ification, code spans.
 * Theming is hand-applied so the rendered text inherits MaterialTheme.colorScheme.onSurface.
 */
@Composable
fun MarkdownText(
    text: String,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val textColorArgb = MaterialTheme.colorScheme.onSurface.toArgb()
    val linkColorArgb = MaterialTheme.colorScheme.primary.toArgb()
    // Theme tokens approximating the iOS `Theme.chatAssistant` (ChatMarkdownTheme.swift):
    // subtle code background, a secondary blockquote bar, a faint heading break.
    val codeBgArgb = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.06f).toArgb()
    val blockQuoteArgb = MaterialTheme.colorScheme.onSurfaceVariant.toArgb()
    val headingBreakArgb = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.12f).toArgb()
    val density = LocalDensity.current
    val blockQuoteWidthPx = with(density) { 3.dp.roundToPx() }
    val headingBreakPx = with(density) { 1.dp.roundToPx() }

    val markwon = remember(
        context, codeBgArgb, blockQuoteArgb, headingBreakArgb, linkColorArgb,
    ) {
        Markwon.builder(context)
            .usePlugin(LinkifyPlugin.create())
            .usePlugin(TablePlugin.create(context))
            .usePlugin(StrikethroughPlugin.create())
            .usePlugin(TaskListPlugin.create(context))
            .usePlugin(object : AbstractMarkwonPlugin() {
                override fun configureTheme(builder: MarkwonTheme.Builder) {
                    builder
                        // code spans + fenced blocks: subtle tinted background (iOS black @ 6%).
                        .codeBackgroundColor(codeBgArgb)
                        .codeBlockBackgroundColor(codeBgArgb)
                        .codeTextColor(textColorArgb)
                        .codeBlockTextColor(textColorArgb)
                        // blockquote: secondary-coloured left bar (iOS Rectangle overlay).
                        .blockQuoteColor(blockQuoteArgb)
                        .blockQuoteWidth(blockQuoteWidthPx)
                        // heading underline break (iOS uses a margin; keep it faint here).
                        .headingBreakColor(headingBreakArgb)
                        .headingBreakHeight(headingBreakPx)
                        // approximate iOS h1/h2/h3 size ramp (1.45 / 1.3 / 1.15 em).
                        .headingTextSizeMultipliers(
                            floatArrayOf(1.45f, 1.3f, 1.15f, 1f, 1f, 1f),
                        )
                        // links pick up the accent color, matching `setLinkTextColor`.
                        .linkColor(linkColorArgb)
                    // Note: table border styling lives on TableTheme (ext-tables), not
                    // MarkwonTheme; TablePlugin.create(context) applies Markwon's default border.
                }
            })
            .build()
    }

    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            TextView(ctx).apply {
                setTextIsSelectable(true)
                textSize = 15f
                setLineSpacing(0f, 1.2f)
                movementMethod = LinkMovementMethod.getInstance()
                layoutParams = ViewGroup.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                )
                // Use the bundled HarmonyOS Sans SC family. The XML maps Bold = 700, so
                // Markwon's StyleSpan(BOLD) picks the actual Bold TTF instead of synth-bold.
                ResourcesCompat.getFont(ctx, R.font.harmony_os_sans_sc)?.let { typeface = it }
            }
        },
        update = { textView ->
            textView.setTextColor(textColorArgb)
            textView.setLinkTextColor(linkColorArgb)
            markwon.setMarkdown(textView, text)
        },
    )
}
