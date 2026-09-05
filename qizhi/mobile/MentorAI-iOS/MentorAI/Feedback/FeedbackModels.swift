import Foundation

/// Mirrors the server `SubmitFeedbackParams`. Star is 1–5; content is required non-empty.
/// `imagePaths` are server-side storage paths returned by `/attachment/upload` (the same
/// endpoint used by chat attachments), so we reuse `AttachmentAPI` instead of inventing
/// a separate uploader.
struct SubmitFeedbackRequest: Encodable {
    var star: Int
    var content: String
    var imagePaths: [String]?

    enum CodingKeys: String, CodingKey {
        case star
        case content
        case imagePaths = "image_paths"
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(star, forKey: .star)
        try c.encode(content, forKey: .content)
        if let imagePaths, !imagePaths.isEmpty {
            try c.encode(imagePaths, forKey: .imagePaths)
        }
    }
}

/// Local attachment state shown in the feedback sheet — same lifecycle pattern as
/// `ChatAttachment`: `.uploading` → `.done(path:)` or `.error(message:)`. Reusing the
/// shared `AttachmentAPI` keeps the upload path consistent across chat + feedback.
struct FeedbackAttachment: Identifiable, Equatable {
    let id: UUID
    let localURL: URL
    let filename: String
    let sizeBytes: Int64
    var status: Status

    init(localURL: URL, filename: String, sizeBytes: Int64, status: Status = .uploading) {
        self.id = UUID()
        self.localURL = localURL
        self.filename = filename
        self.sizeBytes = sizeBytes
        self.status = status
    }

    enum Status: Equatable {
        case uploading
        case done(path: String)
        case error(String)
    }

    var remotePath: String? {
        if case .done(let path) = status { return path }
        return nil
    }

    var isUploading: Bool {
        if case .uploading = status { return true }
        return false
    }

    var displaySize: String {
        let formatter = ByteCountFormatter()
        formatter.allowedUnits = [.useKB, .useMB, .useGB]
        formatter.countStyle = .file
        return formatter.string(fromByteCount: sizeBytes)
    }

    var fileExtension: String {
        (filename as NSString).pathExtension.lowercased()
    }
}

/// Max attachments per submission, matching the web's `maxAttachments` (5).
let FeedbackMaxAttachments: Int = 5
