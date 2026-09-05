import Foundation
import os

@MainActor
final class FeedbackViewModel: ObservableObject {
    @Published var star: Int = 0
    @Published var content: String = ""
    @Published private(set) var attachments: [FeedbackAttachment] = []
    @Published private(set) var isSubmitting: Bool = false
    @Published var submitMessage: String?
    @Published var submitIsError: Bool = false
    @Published var starError: String?
    @Published var contentError: String?
    @Published var attachmentError: String?
    @Published private(set) var didSucceed: Bool = false

    private let feedbackAPI: FeedbackAPI
    private let attachmentAPI: AttachmentAPI
    private let tokenProvider: () -> String?
    private let log = Logger(subsystem: "com.mentorai.app", category: "Feedback")
    private var uploadTasks: [UUID: Task<Void, Never>] = [:]

    init(feedbackAPI: FeedbackAPI,
         attachmentAPI: AttachmentAPI,
         tokenProvider: @escaping () -> String?) {
        self.feedbackAPI = feedbackAPI
        self.attachmentAPI = attachmentAPI
        self.tokenProvider = tokenProvider
    }

    var isUploadingAnyAttachment: Bool {
        attachments.contains { $0.isUploading }
    }

    /// Submit is enabled when both star + content are present, no uploads are in flight,
    /// and we're not already submitting.
    var canSubmit: Bool {
        let hasStar = star >= 1 && star <= 5
        let hasContent = !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return hasStar && hasContent && !isSubmitting && !isUploadingAnyAttachment
    }

    /// Picks up one file URL (from .fileImporter), validates its extension, adds it to the
    /// list in `.uploading` state, and kicks off an upload that updates the status on finish.
    /// Mirrors `ChatViewModel.addAttachment`.
    func addAttachment(localURL: URL) {
        attachmentError = nil

        if attachments.count >= FeedbackMaxAttachments {
            attachmentError = "最多只能上传 \(FeedbackMaxAttachments) 个附件"
            return
        }
        let filename = localURL.lastPathComponent
        guard AttachmentLimits.isAllowed(filename: filename) else {
            attachmentError = "不支持的文件类型：\(filename)"
            return
        }

        let size = (try? FileManager.default.attributesOfItem(atPath: localURL.path)[.size] as? Int64) ?? 0
        let attachment = FeedbackAttachment(localURL: localURL, filename: filename, sizeBytes: size, status: .uploading)
        attachments.append(attachment)
        let attachmentID = attachment.id

        guard let token = tokenProvider(), !token.isEmpty else {
            updateAttachment(id: attachmentID, status: .error("未登录"))
            return
        }

        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            defer { self.uploadTasks[attachmentID] = nil }
            do {
                let path = try await self.attachmentAPI.upload(fileURL: localURL, token: token)
                self.updateAttachment(id: attachmentID, status: .done(path: path))
                self.log.info("Feedback attachment uploaded \(filename, privacy: .public) → \(path, privacy: .public)")
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

    private func updateAttachment(id: UUID, status: FeedbackAttachment.Status) {
        guard let idx = attachments.firstIndex(where: { $0.id == id }) else { return }
        attachments[idx].status = status
    }

    /// Validate + submit. Returns true on success so the caller can dismiss after a brief delay.
    @discardableResult
    func submit() async -> Bool {
        submitMessage = nil
        submitIsError = false
        starError = nil
        contentError = nil
        attachmentError = nil

        let trimmed = content.trimmingCharacters(in: .whitespacesAndNewlines)
        let starOk = star >= 1 && star <= 5
        let contentOk = !trimmed.isEmpty
        if !starOk { starError = "请先选择评分（1–5 星）" }
        if !contentOk { contentError = "请填写反馈与建议后再提交" }
        guard starOk, contentOk else { return false }

        guard let token = tokenProvider(), !token.isEmpty else {
            submitIsError = true
            submitMessage = "未登录"
            return false
        }

        // Only `.done` attachments contribute paths; `.uploading` is blocked by canSubmit,
        // and `.error` attachments are silently skipped (the user can retry by removing them).
        let imagePaths = attachments.compactMap { $0.remotePath }

        isSubmitting = true
        defer { isSubmitting = false }

        do {
            let request = SubmitFeedbackRequest(
                star: star,
                content: trimmed,
                imagePaths: imagePaths.isEmpty ? nil : imagePaths,
            )
            _ = try await feedbackAPI.submit(request, token: token)
            submitIsError = false
            submitMessage = "提交成功，感谢您的反馈"
            didSucceed = true
            return true
        } catch let err as AuthError {
            submitIsError = true
            submitMessage = err.errorDescription ?? "提交失败"
            return false
        } catch {
            submitIsError = true
            submitMessage = error.localizedDescription
            return false
        }
    }
}
