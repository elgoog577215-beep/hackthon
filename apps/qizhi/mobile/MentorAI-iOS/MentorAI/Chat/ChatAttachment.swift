import Foundation

struct ChatAttachment: Identifiable, Equatable {
    let id: UUID
    let localURL: URL
    let filename: String
    let sizeBytes: Int64
    var status: Status

    enum Status: Equatable {
        case uploading
        case done(path: String)
        case error(String)
    }

    init(localURL: URL, filename: String, sizeBytes: Int64, status: Status = .uploading) {
        self.id = UUID()
        self.localURL = localURL
        self.filename = filename
        self.sizeBytes = sizeBytes
        self.status = status
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
        ByteCountFormatter.string(fromByteCount: sizeBytes, countStyle: .file)
    }

    var fileExtension: String {
        (filename as NSString).pathExtension.lowercased()
    }
}
