import Foundation

extension String {
    /// Inserts a thin space (U+2009) around `**`-bold delimiters whose CommonMark flanking
    /// rules would fail next to CJK + ASCII-punctuation boundaries. MarkdownUI follows
    /// CommonMark strictly, so without this fix-up a span like "用于**X(青教赛)**的备赛"
    /// renders the `**` literally — the closing delimiter is preceded by `)` (punctuation)
    /// and followed by `的` (a CJK letter), and CommonMark's right-flanking rule rejects
    /// that combination. U+2009 IS Unicode whitespace, so the closing delimiter then
    /// satisfies clause (b) of the rule. The thin space is visually negligible in CJK text.
    func relaxingCJKBoldFlanking() -> String {
        guard contains("**") else { return self }
        let chars = Array(self)
        let n = chars.count
        var out = String()
        out.reserveCapacity(n + 8)
        var i = 0
        while i < n {
            if i + 1 < n, chars[i] == "*", chars[i + 1] == "*" {
                // Scan for a closing `**` on the same line.
                var j = i + 2
                var foundClose = false
                while j + 1 < n {
                    if chars[j] == "\n" { break }
                    if chars[j] == "*", chars[j + 1] == "*" { foundClose = true; break }
                    j += 1
                }
                if foundClose {
                    let outBefore = i > 0 ? chars[i - 1] : nil       // outside, before opening **
                    let inAfter   = i + 2 < n ? chars[i + 2] : nil   // inside, just after opening
                    let inBefore  = j > 0 ? chars[j - 1] : nil       // inside, just before closing
                    let outAfter  = j + 2 < n ? chars[j + 2] : nil   // outside, after closing **

                    // Open fails left-flanking when preceded by CJK letter and followed by punctuation.
                    let needsOpenPad = outBefore.map(StringMarkdownFixup.isCJKLetter) == true
                        && inAfter.map(StringMarkdownFixup.isMarkdownPunct) == true
                    // Close fails right-flanking when preceded by punctuation and followed by CJK letter.
                    let needsClosePad = inBefore.map(StringMarkdownFixup.isMarkdownPunct) == true
                        && outAfter.map(StringMarkdownFixup.isCJKLetter) == true

                    if needsOpenPad { out.append("\u{2009}") }
                    out.append("**")
                    out.append(contentsOf: chars[(i + 2)..<j])
                    out.append("**")
                    if needsClosePad { out.append("\u{2009}") }
                    i = j + 2
                    continue
                }
            }
            out.append(chars[i])
            i += 1
        }
        return out
    }

    /// Decodes JSON string escape sequences (\n, \t, \r, \", \\, \/, \uXXXX) that arrive
    /// literally in streamed assistant content.
    ///
    /// The backend streams raw slices of the model's JSON `final_answer` field without
    /// decoding them (server `agents/assistant/service.py`), then re-encodes them with
    /// `json.dumps`, so a newline reaches the client as the two characters "\n" rather than
    /// an actual line break — which flattens Markdown (headings, lists, tables) into one line.
    /// Reloaded history is already decoded server-side, so only apply this to live streaming.
    func decodingJSONEscapes() -> String {
        guard contains("\\") else { return self }
        let chars = Array(self)
        var out = String()
        out.reserveCapacity(chars.count)
        var i = 0
        while i < chars.count {
            guard chars[i] == "\\", i + 1 < chars.count else {
                out.append(chars[i]); i += 1; continue
            }
            switch chars[i + 1] {
            case "n": out.append("\n"); i += 2
            case "t": out.append("\t"); i += 2
            case "r": out.append("\r"); i += 2
            case "\"": out.append("\""); i += 2
            case "\\": out.append("\\"); i += 2
            case "/": out.append("/"); i += 2
            case "u" where i + 5 < chars.count:
                let hex = String(chars[(i + 2)...(i + 5)])
                if let code = UInt32(hex, radix: 16), let scalar = Unicode.Scalar(code) {
                    out.append(Character(scalar)); i += 6
                } else {
                    out.append(chars[i]); i += 1
                }
            default:
                out.append(chars[i]); i += 1
            }
        }
        return out
    }
}

/// Predicate helpers for the markdown fix-ups above. Internal so the test target can poke
/// them; otherwise hidden from the rest of the app.
enum StringMarkdownFixup {
    /// CJK letter (Lo/Lm category) across Han, Hangul, Kana — anything CommonMark treats as
    /// "regular character" but visually reads as a word boundary in Chinese/Japanese/Korean.
    static func isCJKLetter(_ c: Character) -> Bool {
        c.unicodeScalars.contains { s in
            (0x3040...0x30FF).contains(s.value) ||   // Hiragana + Katakana
            (0x3400...0x4DBF).contains(s.value) ||   // CJK Ext A
            (0x4E00...0x9FFF).contains(s.value) ||   // CJK Unified Ideographs
            (0xAC00...0xD7AF).contains(s.value) ||   // Hangul syllables
            (0x20000...0x2A6DF).contains(s.value) || // CJK Ext B
            (0x2A700...0x2EBEF).contains(s.value)    // CJK Ext C–F
        }
    }

    /// CommonMark "Unicode punctuation": ASCII punct OR Unicode P* general category.
    static func isMarkdownPunct(_ c: Character) -> Bool {
        let ascii = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
        for scalar in c.unicodeScalars {
            if scalar.isASCII {
                if !ascii.contains(Character(scalar)) { return false }
            } else {
                switch scalar.properties.generalCategory {
                case .connectorPunctuation, .dashPunctuation, .closePunctuation,
                     .finalPunctuation, .initialPunctuation, .otherPunctuation,
                     .openPunctuation: continue
                default: return false
                }
            }
        }
        return true
    }
}
