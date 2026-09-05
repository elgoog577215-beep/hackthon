import Foundation

struct SessionAPI {
    let client: APIClient

    init(baseURL: URL) {
        self.client = URLSessionAPIClient(baseURL: baseURL)
    }

    init(client: APIClient) {
        self.client = client
    }

    func list(token: String) async throws -> [ChatSession] {
        try await client.get("/session/list", query: [], bearerToken: token)
    }

    func detail(id: String, token: String) async throws -> ChatSession {
        try await client.get("/session", query: [URLQueryItem(name: "id", value: id)], bearerToken: token)
    }

    func delete(id: String, token: String) async throws {
        try await client.delete("/session/delete", query: [URLQueryItem(name: "id", value: id)], bearerToken: token)
    }
}
