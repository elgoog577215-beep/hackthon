import Foundation
import os

struct SSEMessage: Equatable {
    var event: String?
    var data: String
}

enum SSEStream {
    private static let log = Logger(subsystem: "com.mentorai.app", category: "SSE")

    static func messages(for request: URLRequest, session: URLSession = .shared) -> AsyncThrowingStream<SSEMessage, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let (bytes, response) = try await session.bytes(for: request)
                    guard let http = response as? HTTPURLResponse else {
                        throw AuthError.transport("SSE 端点返回非 HTTP 响应。")
                    }
                    guard (200..<300).contains(http.statusCode) else {
                        var body = Data()
                        for try await byte in bytes {
                            body.append(byte)
                            if body.count > 4096 { break }
                        }
                        let text = String(data: body, encoding: .utf8) ?? ""
                        log.error("SSE \(http.statusCode, privacy: .public) body=\(text, privacy: .public)")
                        throw AuthError.server(status: http.statusCode, message: text.isEmpty ? nil : text)
                    }

                    var buffer = Data()
                    buffer.reserveCapacity(2048)
                    for try await byte in bytes {
                        if Task.isCancelled { break }
                        buffer.append(byte)
                        while let range = buffer.firstRange(of: Data([0x0A, 0x0A]))
                            ?? buffer.firstRange(of: Data([0x0D, 0x0A, 0x0D, 0x0A])) {
                            let chunk = buffer.subdata(in: 0..<range.lowerBound)
                            buffer.removeSubrange(0..<range.upperBound)
                            if let message = parse(chunk: chunk) {
                                continuation.yield(message)
                            }
                        }
                    }
                    if !buffer.isEmpty {
                        if let message = parse(chunk: buffer) {
                            continuation.yield(message)
                        }
                    }
                    continuation.finish()
                } catch is CancellationError {
                    continuation.finish(throwing: CancellationError())
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }

    private static func parse(chunk: Data) -> SSEMessage? {
        guard let text = String(data: chunk, encoding: .utf8), !text.isEmpty else { return nil }
        // CRLF is a single extended grapheme cluster in Swift, so a Character-based
        // closure split on "\n"/"\r" never fires against "\r\n" line endings (which
        // sse_starlette uses). Normalize before splitting.
        let normalized = text.replacingOccurrences(of: "\r\n", with: "\n")
                              .replacingOccurrences(of: "\r", with: "\n")
        var eventName: String?
        var dataLines: [String] = []
        for rawLine in normalized.split(separator: "\n", omittingEmptySubsequences: false) {
            let line = String(rawLine)
            if line.isEmpty || line.hasPrefix(":") { continue }
            guard let separator = line.firstIndex(of: ":") else {
                continue
            }
            let field = String(line[..<separator])
            var valueStart = line.index(after: separator)
            if valueStart < line.endIndex, line[valueStart] == " " {
                valueStart = line.index(after: valueStart)
            }
            let value = String(line[valueStart...])
            switch field {
            case "event":
                eventName = value
            case "data":
                dataLines.append(value)
            default:
                break
            }
        }
        if dataLines.isEmpty && eventName == nil { return nil }
        return SSEMessage(event: eventName, data: dataLines.joined(separator: "\n"))
    }

    static func parseChatEvent(_ message: SSEMessage) -> ChatEvent? {
        let json = parseJSON(message.data)
        let event = eventName(from: json)
            ?? (message.event ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let resolvedEvent = event.isEmpty ? inferredEventName(from: json, raw: message.data) : event

        switch resolvedEvent {
        case "start":
            if let sid = sessionID(from: json) {
                return .start(sessionID: sid)
            }
            return nil
        case "loading":
            return .loading(text: extractStatusText(from: json, raw: message.data))
        case "thinking":
            return .thinking(text: extractStatusText(from: json, raw: message.data))
        case "message", "chunk":
            if let content = extractMessageContent(from: json, raw: message.data), !content.isEmpty {
                return .message(content: content)
            }
            return nil
        case "card":
            return .card(payload: message.data)
        case "error":
            return .error(message: extractErrorMessage(from: json, raw: message.data))
        case "end", "done":
            return .end
        case "step":
            return nil
        default:
            return nil
        }
    }

    private static func parseJSON(_ raw: String) -> Any? {
        guard let data = raw.data(using: .utf8) else { return nil }
        return try? JSONSerialization.jsonObject(with: data, options: [.fragmentsAllowed])
    }

    private static func eventName(from json: Any?) -> String? {
        guard let json = json as? [String: Any] else { return nil }
        return string(in: json, keys: ["type", "event"])?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
    }

    private static func inferredEventName(from json: Any?, raw: String) -> String {
        if sessionID(from: json) != nil {
            return "start"
        }
        if hasErrorPayload(json) {
            return "error"
        }
        if extractMessageContent(from: json, raw: "")?.isEmpty == false || (json == nil && !raw.isEmpty) {
            return "message"
        }
        return ""
    }

    private static func sessionID(from json: Any?) -> String? {
        for dict in candidateDictionaries(from: json) {
            if let sid = string(in: dict, keys: ["session_id", "sessionId"]), !sid.isEmpty {
                return sid
            }
        }
        return nil
    }

    private static func extractMessageContent(from json: Any?, raw: String) -> String? {
        if let text = json as? String {
            return text
        }
        for dict in candidateDictionaries(from: json) {
            if let content = string(in: dict, keys: ["content", "delta", "text"]) {
                return content
            }
        }
        return raw.isEmpty ? nil : raw
    }

    private static func extractErrorMessage(from json: Any?, raw: String) -> String {
        if let text = json as? String, !text.isEmpty {
            return text
        }
        for dict in candidateDictionaries(from: json) {
            if let msg = string(in: dict, keys: ["error", "message", "detail"]), !msg.isEmpty {
                return msg
            }
        }
        return raw.isEmpty ? "流式响应错误" : raw
    }

    private static func hasErrorPayload(_ json: Any?) -> Bool {
        for dict in candidateDictionaries(from: json) {
            if string(in: dict, keys: ["error"]) != nil {
                return true
            }
        }
        return false
    }

    private static func candidateDictionaries(from json: Any?) -> [[String: Any]] {
        guard let root = json as? [String: Any] else { return [] }
        var dictionaries = [root]
        for key in ["data", "payload", "content"] {
            if let nested = root[key] as? [String: Any] {
                dictionaries.append(nested)
            }
        }
        return dictionaries
    }

    private static func string(in json: [String: Any], keys: [String]) -> String? {
        for k in keys {
            if let v = json[k] as? String, !v.isEmpty {
                return v
            }
        }
        return nil
    }

    private static func extractStatusText(from json: Any?, raw: String) -> String {
        if let text = json as? String, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return text.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        for dict in candidateDictionaries(from: json) {
            if let text = string(in: dict, keys: ["message", "status", "label", "text", "detail", "description", "title", "content"]) {
                return text
            }
            if let step = dict["step"] as? Int {
                if let total = dict["total"] as? Int, total > 0 {
                    return "处理进度 \(step)/\(total)"
                }
                return "步骤 \(step)"
            }
        }
        if json == nil, !raw.isEmpty { return raw }
        return ""
    }
}
