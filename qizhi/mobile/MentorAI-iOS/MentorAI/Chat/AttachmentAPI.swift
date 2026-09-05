import Foundation
import UniformTypeIdentifiers
import os

struct AttachmentAPI {
    let baseURL: URL
    let session: URLSession
    private let log = Logger(subsystem: "com.mentorai.app", category: "Attachment")
    private let decoder: JSONDecoder

    init(baseURL: URL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
        self.decoder = JSONDecoder()
    }

    /// Uploads `fileURL` as multipart/form-data and returns the server-side storage path.
    /// `fileURL` may be a security-scoped URL from `.fileImporter`.
    func upload(fileURL: URL, token: String) async throws -> String {
        let needsScope = fileURL.startAccessingSecurityScopedResource()
        defer { if needsScope { fileURL.stopAccessingSecurityScopedResource() } }

        let fileData: Data
        do {
            fileData = try Data(contentsOf: fileURL)
        } catch {
            throw AuthError.transport("无法读取文件：\(error.localizedDescription)")
        }

        let filename = fileURL.lastPathComponent
        let mimeType = mimeType(for: fileURL)

        let url = try makeURL(path: "attachment/upload")
        let boundary = "Boundary-\(UUID().uuidString)"

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.timeoutInterval = 120
        request.httpBody = multipartBody(boundary: boundary,
                                         fieldName: "file",
                                         filename: filename,
                                         mimeType: mimeType,
                                         data: fileData)

        log.debug("POST \(url.absoluteString, privacy: .public) filename=\(filename, privacy: .public) bytes=\(fileData.count, privacy: .public)")

        let respData: Data
        let response: URLResponse
        do {
            (respData, response) = try await session.data(for: request)
        } catch {
            throw AuthError.transport(error.localizedDescription)
        }

        guard let http = response as? HTTPURLResponse else {
            throw AuthError.transport("收到非 HTTP 响应。")
        }
        let preview = String(data: respData.prefix(500), encoding: .utf8) ?? "<binary>"
        log.debug("← \(http.statusCode) \(preview, privacy: .public)")

        guard (200..<300).contains(http.statusCode) else {
            if let envelope = try? decoder.decode(APIEnvelope<String>.self, from: respData),
               let msg = envelope.errorMessage {
                throw AuthError.server(status: http.statusCode, message: msg)
            }
            throw AuthError.server(status: http.statusCode, message: preview)
        }

        let envelope: APIEnvelope<String>
        do {
            envelope = try decoder.decode(APIEnvelope<String>.self, from: respData)
        } catch {
            throw AuthError.decoding(error.localizedDescription)
        }
        if !envelope.isSuccess {
            throw AuthError.server(status: envelope.code ?? http.statusCode,
                                   message: envelope.errorMessage ?? "上传失败")
        }
        guard let path = envelope.data, !path.isEmpty else {
            throw AuthError.decoding("上传响应缺少存储路径。")
        }
        return path
    }

    private func makeURL(path: String) throws -> URL {
        let trimmed = path.hasPrefix("/") ? String(path.dropFirst()) : path
        let base = baseURL.absoluteString.hasSuffix("/") ? baseURL.absoluteString : baseURL.absoluteString + "/"
        guard let url = URL(string: base + trimmed) else {
            throw AuthError.transport("无法为路径 \(path) 构建有效的 URL。")
        }
        return url
    }

    private func mimeType(for fileURL: URL) -> String {
        if let utType = UTType(filenameExtension: fileURL.pathExtension),
           let preferred = utType.preferredMIMEType {
            return preferred
        }
        return "application/octet-stream"
    }

    private func multipartBody(boundary: String,
                               fieldName: String,
                               filename: String,
                               mimeType: String,
                               data: Data) -> Data {
        var body = Data()
        let crlf = "\r\n"
        body.append("--\(boundary)\(crlf)".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"\(fieldName)\"; filename=\"\(filename)\"\(crlf)".data(using: .utf8)!)
        body.append("Content-Type: \(mimeType)\(crlf)\(crlf)".data(using: .utf8)!)
        body.append(data)
        body.append(crlf.data(using: .utf8)!)
        body.append("--\(boundary)--\(crlf)".data(using: .utf8)!)
        return body
    }
}

enum AttachmentLimits {
    /// Mirrors the web client's `COMMON_ATTACHMENT_EXTENSIONS`.
    static let allowedExtensions: Set<String> = [
        "txt", "md", "pdf",
        "doc", "docx", "ppt", "pptx", "xls", "xlsx",
        "jpg", "jpeg", "png", "gif", "webp", "bmp", "svg",
        "mp4", "webm", "mov", "mkv", "avi", "m4v",
    ]

    static func isAllowed(filename: String) -> Bool {
        let ext = (filename as NSString).pathExtension.lowercased()
        return allowedExtensions.contains(ext)
    }
}
