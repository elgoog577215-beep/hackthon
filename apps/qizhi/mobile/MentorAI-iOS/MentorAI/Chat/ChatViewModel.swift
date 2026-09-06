import Foundation
import SwiftUI
import os

@MainActor
final class ChatViewModel: ObservableObject {
    @Published private(set) var session: ChatSession?
    @Published private(set) var messages: [ChatMessage] = []
    @Published var draft: String = ""
    @Published private(set) var statusText: String?
    @Published private(set) var isStreaming: Bool = false
    @Published var streamError: String?
    @Published private(set) var isLoadingSession: Bool = false
    @Published var sessionError: String?
    @Published private(set) var attachments: [ChatAttachment] = []

    let initialSessionID: String?
    private let chatAPI: ChatAPI
    private let sessionAPI: SessionAPI
    private let attachmentAPI: AttachmentAPI
    private let tokenProvider: () -> String?
    private var streamTask: Task<Void, Never>?
    private var uploadTasks: [UUID: Task<Void, Never>] = [:]
    private let log = Logger(subsystem: "com.mentorai.app", category: "Chat")

    init(sessionID: String?,
         chatAPI: ChatAPI,
         sessionAPI: SessionAPI,
         attachmentAPI: AttachmentAPI,
         tokenProvider: @escaping () -> String?) {
        self.initialSessionID = sessionID
        self.chatAPI = chatAPI
        self.sessionAPI = sessionAPI
        self.attachmentAPI = attachmentAPI
        self.tokenProvider = tokenProvider
    }

    var currentSessionID: String? {
        session?.id ?? initialSessionID
    }

    var titleForDisplay: String {
        if let session, !session.title.isEmpty { return session.title }
        if initialSessionID == nil { return "新对话" }
        return "对话"
    }

    var canSend: Bool {
        let hasText = !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        let hasDoneAttachment = attachments.contains { $0.remotePath != nil }
        let anyUploading = attachments.contains { $0.isUploading }
        return !isStreaming && !anyUploading && (hasText || hasDoneAttachment)
    }

    var isUploadingAnyAttachment: Bool {
        attachments.contains { $0.isUploading }
    }

    func load() async {
        guard let id = initialSessionID else { return }
        guard let token = tokenProvider() else {
            sessionError = "未登录"
            return
        }
        isLoadingSession = true
        sessionError = nil
        defer { isLoadingSession = false }
        do {
            let detail = try await sessionAPI.detail(id: id, token: token)
            session = detail
            messages = detail.messages
            log.info("Loaded session \(id, privacy: .public) with \(detail.messages.count) messages")
        } catch let err as AuthError {
            sessionError = err.errorDescription
        } catch {
            sessionError = error.localizedDescription
        }
    }

    func send() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        let doneAttachments = attachments.filter { $0.remotePath != nil }
        let donePaths = doneAttachments.compactMap { $0.remotePath }
        guard !isStreaming, !isUploadingAnyAttachment, !text.isEmpty || !donePaths.isEmpty else { return }
        guard let token = tokenProvider(), !token.isEmpty else {
            streamError = "未登录"
            return
        }

        draft = ""
        streamError = nil
        statusText = nil

        let displayText = composeUserBubble(text: text, attachments: doneAttachments)
        messages.append(ChatMessage(role: .user, content: displayText))
        messages.append(ChatMessage(role: .assistant, content: ""))
        let assistantIndex = messages.count - 1
        isStreaming = true

        let request = ChatSendRequest(
            sessionID: currentSessionID,
            query: composeQuery(text: text, attachments: doneAttachments),
            filePaths: donePaths.isEmpty ? nil : donePaths,
            extraParams: nil
        )
        log.info("chat/send query.len=\(text.count, privacy: .public) files=\(donePaths.count, privacy: .public) paths=\(donePaths.joined(separator: "|"), privacy: .public)")

        attachments.removeAll()

        streamTask = Task { @MainActor [weak self] in
            guard let self else { return }
            defer {
                // Streamed content carries literal JSON escapes (\n, \" …) from the
                // backend; decode the finished message so it persists correctly after
                // the streaming-tail render-time decode stops applying.
                if assistantIndex < self.messages.count {
                    self.messages[assistantIndex].content =
                        self.messages[assistantIndex].content.decodingJSONEscapes()
                }
                self.isStreaming = false
                self.statusText = nil
                self.streamTask = nil
            }
            do {
                for try await event in self.chatAPI.send(request, token: token) {
                    if Task.isCancelled { break }
                    self.handle(event: event, assistantIndex: assistantIndex)
                    if case .end = event { return }
                    if case .error = event { return }
                }
            } catch is CancellationError {
                self.log.info("Chat stream cancelled")
            } catch let err as AuthError {
                self.streamError = err.errorDescription
                self.log.error("Chat stream failed: \(err.errorDescription ?? "?", privacy: .public)")
            } catch {
                self.streamError = error.localizedDescription
                self.log.error("Chat stream failed: \(error.localizedDescription, privacy: .public)")
            }
        }
    }

    func cancel() {
        streamTask?.cancel()
        streamTask = nil
        isStreaming = false
        statusText = nil
    }

    // MARK: Attachments

    func addAttachment(localURL: URL) {
        let filename = localURL.lastPathComponent
        guard AttachmentLimits.isAllowed(filename: filename) else {
            streamError = "不支持的文件类型：\(filename)"
            return
        }
        let size = (try? FileManager.default.attributesOfItem(atPath: localURL.path)[.size] as? Int64) ?? 0
        var attachment = ChatAttachment(localURL: localURL, filename: filename, sizeBytes: size, status: .uploading)
        attachments.append(attachment)
        let attachmentID = attachment.id

        guard let token = tokenProvider(), !token.isEmpty else {
            attachment.status = .error("未登录")
            updateAttachment(id: attachmentID, status: .error("未登录"))
            return
        }

        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            defer { self.uploadTasks[attachmentID] = nil }
            do {
                let path = try await self.attachmentAPI.upload(fileURL: localURL, token: token)
                self.updateAttachment(id: attachmentID, status: .done(path: path))
                self.log.info("Uploaded attachment \(filename, privacy: .public) → \(path, privacy: .public)")
            } catch is CancellationError {
                self.removeAttachment(id: attachmentID)
            } catch let err as AuthError {
                self.updateAttachment(id: attachmentID, status: .error(err.errorDescription ?? "上传失败"))
            } catch {
                self.updateAttachment(id: attachmentID, status: .error(error.localizedDescription))
            }
        }
        uploadTasks[attachmentID] = task
    }

    func removeAttachment(id: UUID) {
        uploadTasks[id]?.cancel()
        uploadTasks[id] = nil
        attachments.removeAll { $0.id == id }
    }

    private func updateAttachment(id: UUID, status: ChatAttachment.Status) {
        guard let idx = attachments.firstIndex(where: { $0.id == id }) else { return }
        attachments[idx].status = status
    }

    /// Mirrors the web client: append each attachment's name as `[name]` so the
    /// text-only planner can detect the attachment and route to the right tool.
    /// The server never sees `file_paths` during planning, only this query string.
    private func composeQuery(text: String, attachments: [ChatAttachment]) -> String {
        guard !attachments.isEmpty else { return text }
        let fileNames = attachments.map { "[\($0.filename)]" }.joined(separator: " ")
        return text.isEmpty ? fileNames : "\(text)\n\n\(fileNames)"
    }

    private func composeUserBubble(text: String, attachments: [ChatAttachment]) -> String {
        guard !attachments.isEmpty else { return text }
        let lines = attachments.map { "📎 \($0.filename)" }
        let header = lines.joined(separator: "\n")
        if text.isEmpty { return header }
        return header + "\n\n" + text
    }

    private func handle(event: ChatEvent, assistantIndex: Int) {
        switch event {
        case .start(let sid):
            if session == nil {
                session = ChatSession(id: sid, title: "", createTime: "", updateTime: "")
            }
        case .loading(let text), .thinking(let text):
            if !text.isEmpty { statusText = text }
        case .message(let chunk):
            statusText = nil
            guard assistantIndex < messages.count else { return }
            messages[assistantIndex].content += chunk
        case .card:
            break
        case .error(let msg):
            streamError = msg
        case .end:
            statusText = nil
        }
    }
}
