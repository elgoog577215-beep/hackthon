import Foundation

struct AuthAPI {
    let client: APIClient

    init(baseURL: URL) {
        self.client = URLSessionAPIClient(baseURL: baseURL)
    }

    init(client: APIClient) {
        self.client = client
    }

    func authorizationURL() async throws -> AuthURLResponse {
        try await client.get("/auth/url", query: [])
    }

    func exchange(code: String, state: String?) async throws -> AuthCallbackResponse {
        var items: [URLQueryItem] = [URLQueryItem(name: "code", value: code)]
        if let state, !state.isEmpty {
            items.append(URLQueryItem(name: "state", value: state))
        }
        return try await client.get("/auth/callback", query: items)
    }

    func testLogin(name: String, zjuID: String) async throws -> AuthCallbackResponse {
        let items: [URLQueryItem] = [
            URLQueryItem(name: "name", value: name),
            URLQueryItem(name: "zju_id", value: zjuID)
        ]
        return try await client.post("/auth/test-login", query: items)
    }
}
