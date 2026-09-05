import Foundation
import os

/// 视频分析方式。`cloud`=智云课堂(超星)云端分析（默认）；`local`=本地自建模型直接分析。
/// Mirrors the web `AnalysisMode` (`api/video.ts`); sent as the `mode` query param to /video/analyze.
enum AnalysisMode: String {
    case cloud
    case local
}

struct VideoAPI {
    let baseURL: URL
    let client: APIClient
    let streamSession: URLSession
    private let log = Logger(subsystem: "com.mentorai.app", category: "VideoAPI")
    static let chunkSize: Int = 5 * 1024 * 1024  // 5 MB — matches web client

    init(baseURL: URL) {
        self.baseURL = baseURL
        self.client = URLSessionAPIClient(baseURL: baseURL)
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 300
        config.timeoutIntervalForResource = 3600
        self.streamSession = URLSession(configuration: config)
    }

    // MARK: - List + Detail + Operation

    func list(token: String) async throws -> [VideoSummary] {
        try await client.get("/video/list", query: [], bearerToken: token)
    }

    func detail(id: String, token: String) async throws -> VideoDetail {
        try await client.get("/video",
                             query: [URLQueryItem(name: "id", value: id)],
                             bearerToken: token)
    }

    @discardableResult
    func operate(_ params: VideoOperationRequest, token: String) async throws -> String {
        let url = try makeURL(path: "video/operation")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.httpBody = try JSONEncoder().encode(params)

        let (data, response) = try await streamSession.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw AuthError.transport("收到非 HTTP 响应。")
        }
        let bodyPreview = String(data: data.prefix(500), encoding: .utf8) ?? "<binary>"
        log.debug("POST video/operation op=\(params.operation.rawValue, privacy: .public) → \(http.statusCode, privacy: .public) \(bodyPreview, privacy: .public)")
        let decoder = JSONDecoder()
        guard (200..<300).contains(http.statusCode) else {
            if let env = try? decoder.decode(APIEnvelope<String>.self, from: data),
               let msg = env.errorMessage {
                throw AuthError.server(status: http.statusCode, message: msg)
            }
            throw AuthError.server(status: http.statusCode, message: bodyPreview)
        }
        let envelope = try decoder.decode(APIEnvelope<String>.self, from: data)
        if !envelope.isSuccess {
            throw AuthError.server(status: envelope.code ?? http.statusCode,
                                   message: envelope.errorMessage ?? "操作失败")
        }
        return envelope.data ?? ""
    }

    func analyze(id: String, mode: AnalysisMode = .cloud, token: String) async throws {
        let _: EmptyDecodable = try await client.get(
            "/video/analyze",
            query: [
                URLQueryItem(name: "id", value: id),
                URLQueryItem(name: "mode", value: mode.rawValue),
            ],
            bearerToken: token
        )
    }

    // MARK: - Chunked Upload (init → upload → finish)

    struct UploadFinishResult {
        let videoPath: String
        let coverPath: String?
    }

    func initUpload(totalChunks: Int, token: String) async throws -> String {
        let url = try makeURL(path: "video/init")
        let body = "chunks=\(totalChunks)".data(using: .utf8) ?? Data()
        let envelope: APIEnvelope<String> = try await postForm(url: url, body: body, token: token)
        guard envelope.isSuccess, let uploadID = envelope.data, !uploadID.isEmpty else {
            throw AuthError.server(status: envelope.code ?? 500,
                                   message: envelope.errorMessage ?? "初始化上传失败")
        }
        return uploadID
    }

    func uploadChunk(uploadID: String, index: Int, data: Data, filename: String, token: String) async throws {
        let url = try makeURL(path: "video/upload")
        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.timeoutInterval = 300
        request.httpBody = multipartBody(
            boundary: boundary,
            fields: ["upload_id": uploadID, "index": "\(index)"],
            file: (name: "file", filename: filename, mimeType: "application/octet-stream", data: data)
        )

        let (respData, response) = try await streamSession.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw AuthError.transport("收到非 HTTP 响应。")
        }
        guard (200..<300).contains(http.statusCode) else {
            let preview = String(data: respData.prefix(500), encoding: .utf8) ?? ""
            throw AuthError.server(status: http.statusCode, message: preview)
        }
        let envelope = try JSONDecoder().decode(APIEnvelope<EmptyDecodable>.self, from: respData)
        if !envelope.isSuccess {
            throw AuthError.server(status: envelope.code ?? http.statusCode,
                                   message: envelope.errorMessage ?? "分片上传失败")
        }
    }

    func finishUpload(uploadID: String, token: String) async throws -> UploadFinishResult {
        let url = try makeURL(path: "video/finish")
        let body = "upload_id=\(uploadID)".data(using: .utf8) ?? Data()
        let envelope: APIEnvelope<[String: String]> = try await postForm(url: url, body: body, token: token)
        guard envelope.isSuccess, let dict = envelope.data, let path = dict["path"], !path.isEmpty else {
            throw AuthError.server(status: envelope.code ?? 500,
                                   message: envelope.errorMessage ?? "合并上传失败")
        }
        return UploadFinishResult(videoPath: path, coverPath: dict["cover_path"])
    }

    // MARK: - Zhiyun (smart classroom)

    /// `/video/zhiyun/list` now returns courses grouped (`[ZhiyunCourseGroup]`) and only
    /// supports date-range filtering server-side, so we flatten the groups into recording
    /// rows and apply the optional course-name filter on the client.
    func listZhiyunCourses(beginDate: String,
                          endDate: String,
                          courseName: String?,
                          token: String) async throws -> [ZhiyunCourse] {
        let query: [URLQueryItem] = [
            URLQueryItem(name: "search_begin_date", value: beginDate),
            URLQueryItem(name: "search_end_date", value: endDate),
        ]
        let groups: [ZhiyunCourseGroup] = try await client.get(
            "/video/zhiyun/list", query: query, bearerToken: token
        )
        var rows = groups.flatMap { group in
            group.items.map { item in
                ZhiyunCourse(
                    courseID: group.courseID,
                    subID: item.subID,
                    courseName: group.courseName,
                    subTitle: item.subTitle,
                    teacherName: item.teacherName,
                    classBegin: item.classBegin
                )
            }
        }
        if let courseName = courseName?.trimmingCharacters(in: .whitespacesAndNewlines), !courseName.isEmpty {
            rows = rows.filter { $0.courseName.localizedCaseInsensitiveContains(courseName) }
        }
        return rows
    }

    enum ZhiyunImportEvent: Equatable {
        case start(videoID: String)
        case progress(percent: Int)
        case error(String)
        case end(videoID: String?)
    }

    func importZhiyun(courseID: String, subID: String, importID: String, token: String) -> AsyncThrowingStream<ZhiyunImportEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let url = try makeURL(path: "video/zhiyun/import",
                                          query: [
                                            URLQueryItem(name: "course_id", value: courseID),
                                            URLQueryItem(name: "sub_id", value: subID),
                                            // 本次导入标识：配合 cancelZhiyunImport 让后端可中途取消
                                            URLQueryItem(name: "import_id", value: importID),
                                          ])
                    var request = URLRequest(url: url)
                    request.httpMethod = "GET"
                    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
                    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                    request.timeoutInterval = 300

                    log.debug("GET \(url.absoluteString, privacy: .public)")

                    for try await sse in SSEStream.messages(for: request, session: streamSession) {
                        if Task.isCancelled { break }
                        guard let event = Self.parseZhiyunEvent(sse) else { continue }
                        continuation.yield(event)
                        if case .end = event { break }
                        if case .error = event { break }
                    }
                    continuation.finish()
                } catch is CancellationError {
                    continuation.finish(throwing: CancellationError())
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    /// 取消正在进行的智云课堂视频导入。
    ///
    /// 仅取消客户端 SSE 任务并不可靠：反向代理常缓冲上游连接，后端要到下载完成、
    /// 视频已落库后才察觉断开，于是「取消后视频仍出现在列表里」。本接口写一个带外
    /// 取消标记，后端在下一个分片处即停止下载并清理，不落库。best-effort。
    func cancelZhiyunImport(importID: String, token: String) async throws {
        guard !importID.isEmpty else { return }
        let url = try makeURL(path: "video/zhiyun/import/cancel")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.httpBody = try JSONEncoder().encode(["import_id": importID])

        let (data, response) = try await streamSession.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw AuthError.transport("收到非 HTTP 响应。")
        }
        let bodyPreview = String(data: data.prefix(300), encoding: .utf8) ?? "<binary>"
        log.debug("POST video/zhiyun/import/cancel → \(http.statusCode, privacy: .public) \(bodyPreview, privacy: .public)")
        guard (200..<300).contains(http.statusCode) else {
            throw AuthError.server(status: http.statusCode, message: bodyPreview)
        }
    }

    private static func parseZhiyunEvent(_ sse: SSEMessage) -> ZhiyunImportEvent? {
        let event = (sse.event ?? "").lowercased()
        let json = (try? JSONSerialization.jsonObject(with: Data(sse.data.utf8), options: [.fragmentsAllowed])) as? [String: Any]
        switch event {
        case "start":
            if let id = json?["id"] as? String, !id.isEmpty {
                return .start(videoID: id)
            }
            return nil
        case "loading":
            if let p = json?["progress"] as? Int {
                return .progress(percent: p)
            }
            if let p = json?["progress"] as? Double {
                return .progress(percent: Int(p))
            }
            return nil
        case "error":
            let msg = (json?["error"] as? String)
                ?? (json?["message"] as? String)
                ?? sse.data
            return .error(msg.isEmpty ? "导入失败" : msg)
        case "end", "done":
            // The server delivers the new video id in the end event: {"id": "..."}.
            let id = json?["id"] as? String
            return .end(videoID: (id?.isEmpty == false) ? id : nil)
        default:
            return nil
        }
    }

    // MARK: - Helpers

    private func postForm<T: Decodable>(url: URL, body: Data, token: String) async throws -> APIEnvelope<T> {
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.httpBody = body

        let (data, response) = try await streamSession.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw AuthError.transport("收到非 HTTP 响应。")
        }
        let preview = String(data: data.prefix(500), encoding: .utf8) ?? ""
        log.debug("POST \(url.absoluteString, privacy: .public) → \(http.statusCode, privacy: .public) \(preview, privacy: .public)")
        guard (200..<300).contains(http.statusCode) else {
            throw AuthError.server(status: http.statusCode, message: preview)
        }
        return try JSONDecoder().decode(APIEnvelope<T>.self, from: data)
    }

    private func multipartBody(boundary: String,
                               fields: [String: String],
                               file: (name: String, filename: String, mimeType: String, data: Data)) -> Data {
        var body = Data()
        let crlf = "\r\n"
        for (k, v) in fields {
            body.append("--\(boundary)\(crlf)".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"\(k)\"\(crlf)\(crlf)".data(using: .utf8)!)
            body.append("\(v)\(crlf)".data(using: .utf8)!)
        }
        body.append("--\(boundary)\(crlf)".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"\(file.name)\"; filename=\"\(file.filename)\"\(crlf)".data(using: .utf8)!)
        body.append("Content-Type: \(file.mimeType)\(crlf)\(crlf)".data(using: .utf8)!)
        body.append(file.data)
        body.append(crlf.data(using: .utf8)!)
        body.append("--\(boundary)--\(crlf)".data(using: .utf8)!)
        return body
    }

    private func makeURL(path: String, query: [URLQueryItem] = []) throws -> URL {
        let trimmed = path.hasPrefix("/") ? String(path.dropFirst()) : path
        let base = baseURL.absoluteString.hasSuffix("/") ? baseURL.absoluteString : baseURL.absoluteString + "/"
        guard var components = URLComponents(string: base + trimmed) else {
            throw AuthError.transport("URL 组件无效：\(path)。")
        }
        if !query.isEmpty {
            components.queryItems = (components.queryItems ?? []) + query
        }
        guard let url = components.url else {
            throw AuthError.transport("无法为路径 \(path) 构建 URL。")
        }
        return url
    }
}
