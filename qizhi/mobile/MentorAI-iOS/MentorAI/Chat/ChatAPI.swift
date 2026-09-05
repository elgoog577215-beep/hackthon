import Foundation
import os

struct ChatAPI {
    let baseURL: URL
    let session: URLSession
    let log = Logger(subsystem: "com.mentorai.app", category: "ChatAPI")

    init(baseURL: URL) {
        self.baseURL = baseURL
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 300
        configuration.timeoutIntervalForResource = 600
        self.session = URLSession(configuration: configuration)
    }

    init(baseURL: URL, session: URLSession) {
        self.baseURL = baseURL
        self.session = session
    }

    func send(_ request: ChatSendRequest, token: String) -> AsyncThrowingStream<ChatEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    // Backend chat route is POST /ai/chat (server `api/ai.py`, mounted under
                    // the `/ai` prefix); the web client posts to the same path. The request
                    // body shape (query / session_id / file_paths / extra_params) already
                    // matches it — only the path was wrong, which 404'd on this backend.
                    let url = try makeURL(path: "ai/chat")
                    var urlRequest = URLRequest(url: url)
                    urlRequest.httpMethod = "POST"
                    urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    urlRequest.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    urlRequest.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
                    urlRequest.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                    let encoder = JSONEncoder()
                    let bodyData = try encoder.encode(request)
                    urlRequest.httpBody = bodyData
                    urlRequest.timeoutInterval = 300

                    let bodyPreview = String(data: bodyData, encoding: .utf8) ?? "<binary>"
                    log.debug("POST \(url.absoluteString, privacy: .public) body=\(bodyPreview, privacy: .public)")

                    for try await sse in SSEStream.messages(for: urlRequest, session: session) {
                        if Task.isCancelled { break }
                        guard let event = SSEStream.parseChatEvent(sse) else { continue }
                        continuation.yield(event)
                        if case .end = event { break }
                        if case .error = event { break }
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

    private func makeURL(path: String) throws -> URL {
        let trimmed = path.hasPrefix("/") ? String(path.dropFirst()) : path
        let base = baseURL.absoluteString.hasSuffix("/") ? baseURL.absoluteString : baseURL.absoluteString + "/"
        guard let url = URL(string: base + trimmed) else {
            throw AuthError.transport("Invalid URL for path \(path).")
        }
        return url
    }
}
