import Foundation
import os

/// Wraps the backend `/feedback` POST endpoint. Mirrors `client/website/src/api/feedback.ts`
/// — submit star + content + optional `image_paths`, returns the new feedback id.
///
/// `URLSessionAPIClient.post` doesn't accept a JSON body (every existing call site is
/// bodiless), so we build the request manually here, matching the pattern in `VideoAPI`.
struct FeedbackAPI {
    let baseURL: URL
    let session: URLSession
    private let log = Logger(subsystem: "com.mentorai.app", category: "FeedbackAPI")
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init(baseURL: URL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
        self.decoder = JSONDecoder()
        self.encoder = JSONEncoder()
    }

    /// Submits the user's feedback. Returns the new feedback id on success; throws
    /// `AuthError` on transport / server / decoding failures.
    @discardableResult
    func submit(_ params: SubmitFeedbackRequest, token: String) async throws -> String {
        let url = try makeURL(path: "feedback")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.httpBody = try encoder.encode(params)

        log.debug("POST \(url.absoluteString, privacy: .public) star=\(params.star) attachments=\(params.imagePaths?.count ?? 0, privacy: .public)")

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw AuthError.transport(error.localizedDescription)
        }
        guard let http = response as? HTTPURLResponse else {
            throw AuthError.transport("收到非 HTTP 响应。")
        }
        let preview = String(data: data.prefix(500), encoding: .utf8) ?? "<binary>"
        log.debug("← \(http.statusCode) \(preview, privacy: .public)")

        guard (200..<300).contains(http.statusCode) else {
            if let envelope = try? decoder.decode(APIEnvelope<String>.self, from: data),
               let msg = envelope.errorMessage {
                throw AuthError.server(status: http.statusCode, message: msg)
            }
            throw AuthError.server(status: http.statusCode, message: preview)
        }

        let envelope: APIEnvelope<String>
        do {
            envelope = try decoder.decode(APIEnvelope<String>.self, from: data)
        } catch {
            throw AuthError.decoding(error.localizedDescription)
        }
        if !envelope.isSuccess {
            throw AuthError.server(status: envelope.code ?? http.statusCode,
                                   message: envelope.errorMessage ?? "提交反馈失败")
        }
        // Server returns the feedback id in `data` on success; tolerate nil for forward compat.
        return envelope.data ?? ""
    }

    private func makeURL(path: String) throws -> URL {
        let trimmed = path.hasPrefix("/") ? String(path.dropFirst()) : path
        let base = baseURL.absoluteString.hasSuffix("/") ? baseURL.absoluteString : baseURL.absoluteString + "/"
        guard let url = URL(string: base + trimmed) else {
            throw AuthError.transport("无法为路径 \(path) 构建有效的 URL。")
        }
        return url
    }
}
