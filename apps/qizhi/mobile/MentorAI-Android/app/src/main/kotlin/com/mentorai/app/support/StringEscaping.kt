package com.mentorai.app.support

/**
 * Decodes JSON string escape sequences (\n, \t, \r, \", \\, \/, \uXXXX) that arrive literally
 * in streamed assistant chat content. The backend slices the model's JSON final_answer without
 * decoding it (see iOS notes); same problem reaches Android. Apply this on streamed deltas only
 * — loaded history is already decoded server-side.
 */
fun String.decodingJsonEscapes(): String {
    if (!contains('\\')) return this
    val chars = this.toCharArray()
    val out = StringBuilder(chars.size)
    var i = 0
    while (i < chars.size) {
        val c = chars[i]
        if (c == '\\' && i + 1 < chars.size) {
            val next = chars[i + 1]
            when (next) {
                'n' -> { out.append('\n'); i += 2; continue }
                't' -> { out.append('\t'); i += 2; continue }
                'r' -> { out.append('\r'); i += 2; continue }
                '"' -> { out.append('"'); i += 2; continue }
                '\\' -> { out.append('\\'); i += 2; continue }
                '/' -> { out.append('/'); i += 2; continue }
                'u' -> {
                    if (i + 5 < chars.size) {
                        val hex = String(chars, i + 2, 4)
                        val code = hex.toIntOrNull(16)
                        if (code != null) {
                            out.append(code.toChar())
                            i += 6
                            continue
                        }
                    }
                }
            }
        }
        out.append(c)
        i += 1
    }
    return out.toString()
}

/**
 * Inserts a thin space (U+2009) around `**`-bold delimiters whose CommonMark flanking rules would
 * fail next to CJK + ASCII-punctuation boundaries. The Markdown renderer follows CommonMark
 * strictly, so without this fix-up a span like "用于**X(青教赛)**的备赛" renders the `**` literally —
 * the closing delimiter is preceded by `)` (punctuation) and followed by `的` (a CJK letter), and
 * CommonMark's right-flanking rule rejects that combination. U+2009 IS Unicode whitespace, so the
 * closing delimiter then satisfies clause (b) of the rule. The thin space is visually negligible in
 * CJK text. Mirrors iOS `String.relaxingCJKBoldFlanking()`.
 */
fun String.relaxingCJKBoldFlanking(): String {
    if (!contains("**")) return this
    val chars = toCodePointArray()
    val n = chars.size
    val out = StringBuilder(length + 8)
    var i = 0
    while (i < n) {
        if (i + 1 < n && chars[i] == ASTERISK && chars[i + 1] == ASTERISK) {
            // Scan for a closing `**` on the same line.
            var j = i + 2
            var foundClose = false
            while (j + 1 < n) {
                if (chars[j] == NEWLINE) break
                if (chars[j] == ASTERISK && chars[j + 1] == ASTERISK) { foundClose = true; break }
                j += 1
            }
            if (foundClose) {
                val outBefore = if (i > 0) chars[i - 1] else null       // outside, before opening **
                val inAfter = if (i + 2 < n) chars[i + 2] else null     // inside, just after opening
                val inBefore = if (j > 0) chars[j - 1] else null        // inside, just before closing
                val outAfter = if (j + 2 < n) chars[j + 2] else null    // outside, after closing **

                // Open fails left-flanking when preceded by CJK letter and followed by punctuation.
                val needsOpenPad = outBefore != null && MarkdownFixup.isCJKLetter(outBefore) &&
                    inAfter != null && MarkdownFixup.isMarkdownPunct(inAfter)
                // Close fails right-flanking when preceded by punctuation and followed by CJK letter.
                val needsClosePad = inBefore != null && MarkdownFixup.isMarkdownPunct(inBefore) &&
                    outAfter != null && MarkdownFixup.isCJKLetter(outAfter)

                if (needsOpenPad) out.append(' ')
                out.append("**")
                for (k in (i + 2) until j) out.appendCodePoint(chars[k])
                out.append("**")
                if (needsClosePad) out.append(' ')
                i = j + 2
                continue
            }
        }
        out.appendCodePoint(chars[i])
        i += 1
    }
    return out.toString()
}

private val ASTERISK: Int = '*'.code
private val NEWLINE: Int = '\n'.code

/** Decomposes the string into Unicode code points so surrogate pairs (CJK Ext B+) compare correctly. */
private fun String.toCodePointArray(): IntArray {
    val result = ArrayList<Int>(length)
    var idx = 0
    while (idx < length) {
        val cp = codePointAt(idx)
        result.add(cp)
        idx += Character.charCount(cp)
    }
    return result.toIntArray()
}

/**
 * Predicate helpers for the Markdown fix-up above. Mirrors iOS `StringMarkdownFixup`; kept internal
 * so a future test target can exercise them while staying hidden from the rest of the app.
 */
internal object MarkdownFixup {
    /**
     * CJK letter (Lo/Lm category) across Han, Hangul, Kana — anything CommonMark treats as a
     * "regular character" but which visually reads as a word boundary in Chinese/Japanese/Korean.
     */
    fun isCJKLetter(cp: Int): Boolean =
        cp in 0x3040..0x30FF ||    // Hiragana + Katakana
        cp in 0x3400..0x4DBF ||    // CJK Ext A
        cp in 0x4E00..0x9FFF ||    // CJK Unified Ideographs
        cp in 0xAC00..0xD7AF ||    // Hangul syllables
        cp in 0x20000..0x2A6DF ||  // CJK Ext B
        cp in 0x2A700..0x2EBEF     // CJK Ext C–F

    /** CommonMark "Unicode punctuation": ASCII punctuation OR a Unicode P* general category. */
    fun isMarkdownPunct(cp: Int): Boolean {
        if (cp < 0x80) return cp.toChar() in ASCII_PUNCT
        return when (Character.getType(cp)) {
            Character.CONNECTOR_PUNCTUATION.toInt(),
            Character.DASH_PUNCTUATION.toInt(),
            Character.END_PUNCTUATION.toInt(),
            Character.FINAL_QUOTE_PUNCTUATION.toInt(),
            Character.INITIAL_QUOTE_PUNCTUATION.toInt(),
            Character.OTHER_PUNCTUATION.toInt(),
            Character.START_PUNCTUATION.toInt() -> true
            else -> false
        }
    }

    private const val ASCII_PUNCT = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
}
