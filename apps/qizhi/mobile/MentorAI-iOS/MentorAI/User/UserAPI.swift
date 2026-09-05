import Foundation

struct UserAPI {
    let client: APIClient

    init(baseURL: URL) {
        self.client = URLSessionAPIClient(baseURL: baseURL)
    }

    init(client: APIClient) {
        self.client = client
    }

    func currentUser(token: String) async throws -> UserProfile {
        try await client.get("/user/current", query: [], bearerToken: token)
    }
}
