import Foundation
import os

protocol APIClient {
    func get<T: Decodable>(_ path: String, query: [URLQueryItem], bearerToken: String?) async throws -> T
    func post<T: Decodable>(_ path: String, query: [URLQueryItem], bearerToken: String?) async throws -> T
    func delete(_ path: String, query: [URLQueryItem], bearerToken: String?) async throws
}

extension APIClient {
    func get<T: Decodable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        try await get(path, query: query, bearerToken: nil)
    }
    func post<T: Decodable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        try await post(path, query: query, bearerToken: nil)
    }
}

struct URLSessionAPIClient: APIClient {
    let baseURL: URL
    let session: URLSession
    let decoder: JSONDecoder
    let log = Logger(subsystem: "com.mentorai.app", category: "APIClient")

    init(baseURL: URL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .useDefaultKeys
        self.decoder = decoder
    }

    func get<T: Decodable>(_ path: String, query: [URLQueryItem] = [], bearerToken: String? = nil) async throws -> T {
        let url = try makeURL(path: path, query: query)
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let bearerToken, !bearerToken.isEmpty {
            request.setValue("Bearer \(bearerToken)", forHTTPHeaderField: "Authorization")
        }

        log.debug("GET \(url.absoluteString, privacy: .public) authed=\(bearerToken != nil, privacy: .public)")

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            log.error("transport error: \(error.localizedDescription, privacy: .public)")
            throw AuthError.transport(error.localizedDescription)
        }

        guard let http = response as? HTTPURLResponse else {
            throw AuthError.transport("收到非 HTTP 响应。")
        }
        let bodyPreview = String(data: data.prefix(500), encoding: .utf8) ?? "<binary>"
        log.debug("← \(http.statusCode) \(bodyPreview, privacy: .public)")

        guard (200..<300).contains(http.statusCode) else {
            if let envelope = try? decoder.decode(APIEnvelope<T>.self, from: data), let serverMsg = envelope.errorMessage {
                throw AuthError.server(status: http.statusCode, message: serverMsg)
            }
            throw AuthError.server(status: http.statusCode, message: bodyPreview)
        }

        if let envelope = try? decoder.decode(APIEnvelope<T>.self, from: data) {
            if !envelope.isSuccess {
                throw AuthError.server(status: envelope.code ?? http.statusCode, message: envelope.errorMessage)
            }
            if let inner = envelope.data { return inner }
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch let error as DecodingError {
            throw AuthError.decoding(decodingErrorDescription(error))
        } catch {
            throw AuthError.decoding(error.localizedDescription)
        }
    }

    func post<T: Decodable>(_ path: String, query: [URLQueryItem] = [], bearerToken: String? = nil) async throws -> T {
        let url = try makeURL(path: path, query: query)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let bearerToken, !bearerToken.isEmpty {
            request.setValue("Bearer \(bearerToken)", forHTTPHeaderField: "Authorization")
        }

        log.debug("POST \(url.absoluteString, privacy: .public) authed=\(bearerToken != nil, privacy: .public)")

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            log.error("transport error: \(error.localizedDescription, privacy: .public)")
            throw AuthError.transport(error.localizedDescription)
        }

        guard let http = response as? HTTPURLResponse else {
            throw AuthError.transport("收到非 HTTP 响应。")
        }
        let bodyPreview = String(data: data.prefix(500), encoding: .utf8) ?? "<binary>"
        log.debug("← \(http.statusCode) \(bodyPreview, privacy: .public)")

        guard (200..<300).contains(http.statusCode) else {
            if let envelope = try? decoder.decode(APIEnvelope<T>.self, from: data), let serverMsg = envelope.errorMessage {
                throw AuthError.server(status: http.statusCode, message: serverMsg)
            }
            throw AuthError.server(status: http.statusCode, message: bodyPreview)
        }

        if let envelope = try? decoder.decode(APIEnvelope<T>.self, from: data) {
            if !envelope.isSuccess {
                throw AuthError.server(status: envelope.code ?? http.statusCode, message: envelope.errorMessage)
            }
            if let inner = envelope.data { return inner }
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch let error as DecodingError {
            throw AuthError.decoding(decodingErrorDescription(error))
        } catch {
            throw AuthError.decoding(error.localizedDescription)
        }
    }

    func delete(_ path: String, query: [URLQueryItem] = [], bearerToken: String? = nil) async throws {
        let url = try makeURL(path: path, query: query)
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let bearerToken, !bearerToken.isEmpty {
            request.setValue("Bearer \(bearerToken)", forHTTPHeaderField: "Authorization")
        }

        log.debug("DELETE \(url.absoluteString, privacy: .public) authed=\(bearerToken != nil, privacy: .public)")

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            log.error("transport error: \(error.localizedDescription, privacy: .public)")
            throw AuthError.transport(error.localizedDescription)
        }

        guard let http = response as? HTTPURLResponse else {
            throw AuthError.transport("收到非 HTTP 响应。")
        }
        let bodyPreview = String(data: data.prefix(500), encoding: .utf8) ?? "<binary>"
        log.debug("← \(http.statusCode) \(bodyPreview, privacy: .public)")

        guard (200..<300).contains(http.statusCode) else {
            if let envelope = try? decoder.decode(APIEnvelope<EmptyDecodable>.self, from: data),
               let serverMsg = envelope.errorMessage {
                throw AuthError.server(status: http.statusCode, message: serverMsg)
            }
            throw AuthError.server(status: http.statusCode, message: bodyPreview)
        }

        if let envelope = try? decoder.decode(APIEnvelope<EmptyDecodable>.self, from: data),
           !envelope.isSuccess {
            throw AuthError.server(status: envelope.code ?? http.statusCode, message: envelope.errorMessage)
        }
    }

    private func makeURL(path: String, query: [URLQueryItem]) throws -> URL {
        let trimmed = path.hasPrefix("/") ? String(path.dropFirst()) : path
        let base = baseURL.absoluteString.hasSuffix("/") ? baseURL.absoluteString : baseURL.absoluteString + "/"
        guard var components = URLComponents(string: base + trimmed) else {
            throw AuthError.transport("URL 组件无效：\(path)。")
        }
        if !query.isEmpty {
            components.queryItems = (components.queryItems ?? []) + query
        }
        guard let url = components.url else {
            throw AuthError.transport("无法为路径 \(path) 构建 URL。")
        }
        return url
    }

    private func decodingErrorDescription(_ error: DecodingError) -> String {
        switch error {
        case .typeMismatch(_, let ctx),
             .valueNotFound(_, let ctx),
             .keyNotFound(_, let ctx),
             .dataCorrupted(let ctx):
            return ctx.debugDescription
        @unknown default:
            return error.localizedDescription
        }
    }
}
