import Foundation
import os

struct AuthService {
    var signIn: () async throws -> AuthSession

    static let live: AuthService = .make(config: .default)
    private static let log = Logger(subsystem: "com.mentorai.app", category: "AuthService")

    static func make(config: AuthConfig) -> AuthService {
        let api = AuthAPI(baseURL: config.apiBaseURL)
        return AuthService {
            try await Self.run(api: api)
        }
    }

    @MainActor
    private static func run(api: AuthAPI) async throws -> AuthSession {
        log.info("Fetching auth URL…")
        let urlResponse = try await api.authorizationURL()
        log.info("Auth URL: \(urlResponse.url.absoluteString, privacy: .public)")
        guard let redirectURI = urlResponse.redirectURI else {
            log.error("redirect_uri missing from auth URL query")
            throw AuthError.invalidAuthURL
        }
        log.info("Redirect URI: \(redirectURI.absoluteString, privacy: .public)")

        let webAuth = WebAuthSession()
        let callbackURL = try await webAuth.start(
            authURL: urlResponse.url,
            redirectURI: redirectURI
        )
        log.info("Intercepted callback URL: \(callbackURL.absoluteString, privacy: .public)")

        let (code, state) = try Self.extractCodeAndState(from: callbackURL)
        log.info("Extracted code (length=\(code.count)) state=\(state ?? "nil", privacy: .public)")
        let exchangeState = state ?? urlResponse.state
        log.info("Exchanging code for token…")
        let response = try await api.exchange(code: code, state: exchangeState)
        log.info("Session acquired (token length=\(response.session.accessToken.count))")
        return response.session
    }

    static func extractCodeAndState(from url: URL) throws -> (code: String, state: String?) {
        guard var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            throw AuthError.invalidAuthURL
        }
        var items = components.queryItems ?? []
        if items.isEmpty, let fragment = components.fragment {
            components.query = fragment
            items = components.queryItems ?? []
        }
        if let serverError = items.first(where: { $0.name == "error" })?.value {
            throw AuthError.server(status: -1, message: serverError)
        }
        guard let code = items.first(where: { $0.name == "code" })?.value, !code.isEmpty else {
            throw AuthError.missingAuthorizationCode
        }
        let state = items.first(where: { $0.name == "state" })?.value
        return (code, state)
    }
}
