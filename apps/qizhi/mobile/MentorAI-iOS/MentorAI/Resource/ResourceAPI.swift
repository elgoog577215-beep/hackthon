import Foundation
import os

struct ResourceAPI {
    let baseURL: URL
    let client: APIClient
    private let log = Logger(subsystem: "com.mentorai.app", category: "ResourceAPI")
    private let streamSession: URLSession

    init(baseURL: URL) {
        self.baseURL = baseURL
        self.client = URLSessionAPIClient(baseURL: baseURL)
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 300
        config.timeoutIntervalForResource = 600
        self.streamSession = URLSession(configuration: config)
    }

    // MARK: List + Detail

    func list(userID: String?,
              resourceType: ResourceType?,
              keyword: String?,
              token: String) async throws -> [ResourceSummary] {
        var query: [URLQueryItem] = []
        if let userID, !userID.isEmpty {
            query.append(URLQueryItem(name: "user_id", value: userID))
        }
        if let resourceType {
            query.append(URLQueryItem(name: "resource_type", value: resourceType.rawValue))
        }
        if let keyword, !keyword.isEmpty {
            query.append(URLQueryItem(name: "keyword", value: keyword))
        }
        return try await client.get("/resource/list", query: query, bearerToken: token)
    }

    func detail(id: String, token: String) async throws -> ResourceDetail {
        try await client.get("/resource",
                             query: [URLQueryItem(name: "id", value: id)],
                             bearerToken: token)
    }

    // MARK: Operate (create/update/delete/copy)

    func operate(_ params: ResourceOperationRequest, token: String) async throws -> String {
        let url = try makeURL(path: "resource/operation")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.httpBody = try JSONEncoder().encode(params)

        let (data, response) = try await streamSession.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw AuthError.transport("收到非 HTTP 响应。")
        }
        let preview = String(data: data.prefix(500), encoding: .utf8) ?? "<binary>"
        log.debug("POST resource/operation \(params.operation.rawValue, privacy: .public) → \(http.statusCode, privacy: .public) \(preview, privacy: .public)")

        let decoder = JSONDecoder()
        guard (200..<300).contains(http.statusCode) else {
            if let env = try? decoder.decode(APIEnvelope<String>.self, from: data),
               let msg = env.errorMessage {
                throw AuthError.server(status: http.statusCode, message: msg)
            }
            throw AuthError.server(status: http.statusCode, message: preview)
        }
        let envelope = try decoder.decode(APIEnvelope<String>.self, from: data)
        if !envelope.isSuccess {
            throw AuthError.server(status: envelope.code ?? http.statusCode,
                                   message: envelope.errorMessage ?? "操作失败")
        }
        return envelope.data ?? ""
    }

    // MARK: Generate (SSE)

    func generate(_ params: ResourceGenerateRequest, token: String) -> AsyncThrowingStream<ChatEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let url = try makeURL(path: "resource/generate")
                    var request = URLRequest(url: url)
                    request.httpMethod = "POST"
                    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
                    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                    request.timeoutInterval = 300

                    let body = try JSONEncoder().encode(params)
                    request.httpBody = body
                    let bodyPreview = String(data: body, encoding: .utf8) ?? "<binary>"
                    log.debug("POST resource/generate body=\(bodyPreview, privacy: .public)")

                    for try await sse in SSEStream.messages(for: request, session: streamSession) {
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
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    private func makeURL(path: String) throws -> URL {
        let trimmed = path.hasPrefix("/") ? String(path.dropFirst()) : path
        let base = baseURL.absoluteString.hasSuffix("/") ? baseURL.absoluteString : baseURL.absoluteString + "/"
        guard let url = URL(string: base + trimmed) else {
            throw AuthError.transport("无法为路径 \(path) 构建 URL。")
        }
        return url
    }
}
