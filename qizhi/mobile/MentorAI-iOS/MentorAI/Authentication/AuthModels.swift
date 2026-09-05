import Foundation

struct AuthURLResponse: Decodable {
    let url: URL
    let state: String?

    init(from decoder: Decoder) throws {
        if let singleValue = try? decoder.singleValueContainer(),
           let raw = try? singleValue.decode(String.self),
           let url = URL(string: raw) {
            self.url = url
            self.state = nil
            return
        }

        let container = try decoder.container(keyedBy: AnyStringKey.self)
        let urlKeys = [
            "url", "authUrl", "auth_url",
            "redirect", "redirectUrl", "redirect_url",
            "authorizeUrl", "authorize_url",
            "loginUrl", "login_url",
            "oauthUrl", "oauth_url",
            "ssoUrl", "sso_url",
            "link", "href"
        ]
        guard let raw = container.firstString(urlKeys), let url = URL(string: raw) else {
            throw DecodingError.dataCorrupted(.init(
                codingPath: decoder.codingPath,
                debugDescription: "/auth/url 响应缺少 url 字段（已尝试纯字符串及字段：\(urlKeys.joined(separator: "、"))）"
            ))
        }
        self.url = url
        self.state = container.firstString(["state"])
    }
}

extension AuthURLResponse {
    var redirectURI: URL? {
        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return nil }
        guard let raw = components.queryItems?.first(where: { $0.name == "redirect_uri" })?.value else { return nil }
        return URL(string: raw)
    }
}

struct AuthSession: Codable, Equatable {
    var accessToken: String
    var refreshToken: String?
    var tokenType: String?
    var expiresAt: Date?
    var user: AuthUser?

    var isExpired: Bool {
        guard let expiresAt else { return false }
        return expiresAt <= Date().addingTimeInterval(30)
    }
}

struct AuthUser: Codable, Equatable {
    var id: String?
    var username: String?
    var name: String?
    var email: String?
    var avatarURL: URL?

    init(id: String? = nil, username: String? = nil, name: String? = nil, email: String? = nil, avatarURL: URL? = nil) {
        self.id = id
        self.username = username
        self.name = name
        self.email = email
        self.avatarURL = avatarURL
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AnyStringKey.self)
        id = c.firstString(["id", "userId", "user_id", "uid"])
        username = c.firstString(["username", "userName", "user_name", "account", "loginName", "login_name"])
        name = c.firstString(["name", "displayName", "display_name", "nickname", "realName", "real_name"])
        email = c.firstString(["email", "mail"])
        if let s = c.firstString(["avatarUrl", "avatar_url", "avatar"]) {
            avatarURL = URL(string: s)
        }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: AnyStringKey.self)
        try c.encodeIfPresent(id, name: "id")
        try c.encodeIfPresent(username, name: "username")
        try c.encodeIfPresent(name, name: "name")
        try c.encodeIfPresent(email, name: "email")
        try c.encodeIfPresent(avatarURL?.absoluteString, name: "avatarUrl")
    }
}

struct AuthCallbackResponse: Decodable {
    let session: AuthSession

    init(from decoder: Decoder) throws {
        if let singleValue = try? decoder.singleValueContainer(),
           let token = try? singleValue.decode(String.self), !token.isEmpty {
            session = AuthSession(accessToken: token)
            return
        }

        let c = try decoder.container(keyedBy: AnyStringKey.self)
        let accessToken = c.firstString([
            "access_token", "accessToken", "token", "jwt",
            "id_token", "idToken"
        ])
        guard let accessToken else {
            throw DecodingError.dataCorrupted(.init(
                codingPath: decoder.codingPath,
                debugDescription: "/auth/callback 响应中未找到 access token"
            ))
        }
        let refreshToken = c.firstString(["refresh_token", "refreshToken"])
        let tokenType = c.firstString(["token_type", "tokenType"])
        let expiresAt: Date? = {
            if let iso = c.firstString(["expires_at", "expiresAt"]),
               let date = AuthCallbackResponse.iso8601.date(from: iso) {
                return date
            }
            if let secs = c.firstInt(["expires_in", "expiresIn"]) {
                return Date().addingTimeInterval(TimeInterval(secs))
            }
            return nil
        }()
        let user: AuthUser? = c.firstDecodable(AuthUser.self, ["user", "userInfo", "user_info", "profile"])
        session = AuthSession(
            accessToken: accessToken,
            refreshToken: refreshToken,
            tokenType: tokenType,
            expiresAt: expiresAt,
            user: user
        )
    }

    static let iso8601: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
}
