import Foundation
import os

@MainActor
final class SessionListViewModel: ObservableObject {
    @Published private(set) var sessions: [ChatSession] = []
    @Published private(set) var isLoading: Bool = false
    @Published var error: String?

    private let api: SessionAPI
    private let tokenProvider: () -> String?
    private let log = Logger(subsystem: "com.mentorai.app", category: "SessionList")

    init(api: SessionAPI, tokenProvider: @escaping () -> String?) {
        self.api = api
        self.tokenProvider = tokenProvider
    }

    func refresh() async {
        guard let token = tokenProvider(), !token.isEmpty else {
            error = "未登录"
            return
        }
        isLoading = true
        error = nil
        defer { isLoading = false }
        do {
            let list = try await api.list(token: token)
            sessions = list.sorted { $0.sortKey > $1.sortKey }
            log.info("Loaded \(list.count) sessions")
        } catch let err as AuthError {
            error = err.errorDescription
            log.error("Session list failed: \(err.errorDescription ?? "?", privacy: .public)")
        } catch {
            self.error = error.localizedDescription
            log.error("Session list failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func upsert(_ session: ChatSession) {
        if let idx = sessions.firstIndex(where: { $0.id == session.id }) {
            sessions[idx] = session
        } else {
            sessions.insert(session, at: 0)
        }
        sessions.sort { $0.sortKey > $1.sortKey }
    }

    func delete(id: String) async {
        guard let token = tokenProvider(), !token.isEmpty else {
            error = "未登录"
            return
        }
        guard let idx = sessions.firstIndex(where: { $0.id == id }) else { return }
        let removed = sessions.remove(at: idx)
        do {
            try await api.delete(id: id, token: token)
            log.info("Deleted session \(id, privacy: .public)")
        } catch let err as AuthError {
            sessions.insert(removed, at: idx)
            sessions.sort { $0.sortKey > $1.sortKey }
            error = err.errorDescription
            log.error("Delete failed: \(err.errorDescription ?? "?", privacy: .public)")
        } catch {
            sessions.insert(removed, at: idx)
            sessions.sort { $0.sortKey > $1.sortKey }
            self.error = error.localizedDescription
            log.error("Delete failed: \(error.localizedDescription, privacy: .public)")
        }
    }
}
