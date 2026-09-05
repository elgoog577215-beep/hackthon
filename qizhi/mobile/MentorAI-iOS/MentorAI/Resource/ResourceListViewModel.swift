import Foundation
import os

@MainActor
final class ResourceListViewModel: ObservableObject {
    @Published private(set) var resources: [ResourceSummary] = []
    @Published private(set) var isLoading: Bool = false
    @Published var error: String?
    @Published var filterType: ResourceType?
    @Published var keyword: String = ""

    private let api: ResourceAPI
    private let tokenProvider: () -> String?
    private let userIDProvider: () -> String?
    private let log = Logger(subsystem: "com.mentorai.app", category: "ResourceList")

    init(api: ResourceAPI,
         tokenProvider: @escaping () -> String?,
         userIDProvider: @escaping () -> String?) {
        self.api = api
        self.tokenProvider = tokenProvider
        self.userIDProvider = userIDProvider
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
            let list = try await api.list(
                userID: userIDProvider(),
                resourceType: filterType,
                keyword: keyword.isEmpty ? nil : keyword,
                token: token
            )
            resources = list.sorted { ($0.updateTime) > ($1.updateTime) }
            log.info("Loaded \(list.count) resources type=\(self.filterType?.rawValue ?? "all", privacy: .public)")
        } catch let err as AuthError {
            error = err.errorDescription
        } catch {
            self.error = error.localizedDescription
        }
    }

    func delete(id: String) async {
        guard let token = tokenProvider(), !token.isEmpty else { return }
        guard let idx = resources.firstIndex(where: { $0.id == id }) else { return }
        let removed = resources.remove(at: idx)
        do {
            _ = try await api.operate(
                ResourceOperationRequest(operation: .delete, id: id),
                token: token
            )
            log.info("Deleted resource \(id, privacy: .public)")
        } catch let err as AuthError {
            resources.insert(removed, at: idx)
            resources.sort { $0.updateTime > $1.updateTime }
            error = err.errorDescription
        } catch {
            resources.insert(removed, at: idx)
            resources.sort { $0.updateTime > $1.updateTime }
            self.error = error.localizedDescription
        }
    }

    func insert(_ summary: ResourceSummary) {
        if let idx = resources.firstIndex(where: { $0.id == summary.id }) {
            resources[idx] = summary
        } else {
            resources.insert(summary, at: 0)
        }
        resources.sort { $0.updateTime > $1.updateTime }
    }
}
