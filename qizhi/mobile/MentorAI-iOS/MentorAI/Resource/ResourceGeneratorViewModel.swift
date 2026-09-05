import Foundation
import os

@MainActor
final class ResourceGeneratorViewModel: ObservableObject {
    enum Phase: Equatable {
        case idle
        case streaming
        case finished
        case failed(String)
    }

    @Published private(set) var content: String = ""
    @Published private(set) var phase: Phase = .idle
    @Published private(set) var statusText: String?
    @Published var resourceName: String = ""
    @Published private(set) var savedResourceID: String?
    @Published var saveError: String?

    let resourceType: ResourceType
    private let request: ResourceGenerateRequest
    private let api: ResourceAPI
    private let tokenProvider: () -> String?
    private var streamTask: Task<Void, Never>?
    private let log = Logger(subsystem: "com.mentorai.app", category: "ResourceGen")

    init(request: ResourceGenerateRequest,
         defaultName: String,
         api: ResourceAPI,
         tokenProvider: @escaping () -> String?) {
        self.request = request
        self.resourceType = request.resourceType
        self.resourceName = defaultName
        self.api = api
        self.tokenProvider = tokenProvider
    }

    var isStreaming: Bool {
        if case .streaming = phase { return true }
        return false
    }

    var canSave: Bool {
        if case .finished = phase {
            return !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                && !resourceName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                && savedResourceID == nil
        }
        return false
    }

    var wordCount: Int {
        content.count
    }

    func start() {
        guard case .idle = phase else { return }
        guard let token = tokenProvider(), !token.isEmpty else {
            phase = .failed("未登录")
            return
        }
        content = ""
        statusText = nil
        phase = .streaming
        streamTask = Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                for try await event in self.api.generate(self.request, token: token) {
                    if Task.isCancelled { break }
                    self.handle(event)
                    if case .end = event { break }
                    if case .error = event { break }
                }
                if case .streaming = self.phase {
                    self.phase = .finished
                }
                self.statusText = nil
                self.streamTask = nil
            } catch is CancellationError {
                self.log.info("Resource stream cancelled")
                self.phase = .finished
                self.statusText = nil
                self.streamTask = nil
            } catch let err as AuthError {
                self.phase = .failed(err.errorDescription ?? "生成失败")
                self.streamTask = nil
            } catch {
                self.phase = .failed(error.localizedDescription)
                self.streamTask = nil
            }
        }
    }

    func cancel() {
        streamTask?.cancel()
        streamTask = nil
    }

    func retry() {
        cancel()
        content = ""
        phase = .idle
        savedResourceID = nil
        saveError = nil
        start()
    }

    func save() async {
        guard canSave else { return }
        guard let token = tokenProvider(), !token.isEmpty else {
            saveError = "未登录"
            return
        }
        let trimmedName = resourceName.trimmingCharacters(in: .whitespacesAndNewlines)
        let params = ResourceOperationRequest(
            operation: .create,
            id: nil,
            name: trimmedName,
            resourceType: resourceType,
            content: content
        )
        do {
            let newID = try await api.operate(params, token: token)
            savedResourceID = newID
            log.info("Saved resource id=\(newID, privacy: .public) name=\(trimmedName, privacy: .public)")
        } catch let err as AuthError {
            saveError = err.errorDescription
        } catch {
            saveError = error.localizedDescription
        }
    }

    private func handle(_ event: ChatEvent) {
        switch event {
        case .start:
            statusText = "正在准备…"
        case .loading(let text), .thinking(let text):
            if !text.isEmpty { statusText = text }
        case .message(let chunk):
            statusText = nil
            content += chunk
        case .card:
            break
        case .error(let msg):
            phase = .failed(msg)
        case .end:
            statusText = nil
            if case .streaming = phase { phase = .finished }
        }
    }
}
