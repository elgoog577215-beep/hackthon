import Foundation
import os

@MainActor
final class VideoListViewModel: ObservableObject {
    @Published private(set) var videos: [VideoSummary] = []
    @Published private(set) var isLoading: Bool = false
    @Published var error: String?

    private let api: VideoAPI
    private let tokenProvider: () -> String?
    private let log = Logger(subsystem: "com.mentorai.app", category: "VideoList")

    init(api: VideoAPI, tokenProvider: @escaping () -> String?) {
        self.api = api
        self.tokenProvider = tokenProvider
    }

    /// True while any video is still analyzing (WAITING). Drives the list's auto-poll so a
    /// 分析中 row flips to 已完成 / 分析失败 (and the count re-syncs) without a manual pull.
    var hasAnalyzingVideos: Bool {
        videos.contains { $0.status == .waiting }
    }

    /// `silent` is used by the auto-poll: it won't toggle the loading spinner, surface
    /// transient errors, or clear the current list — a failed poll just leaves things as-is.
    func refresh(silent: Bool = false) async {
        guard let token = tokenProvider(), !token.isEmpty else {
            if !silent { error = "未登录" }
            return
        }
        if !silent {
            isLoading = true
            error = nil
        }
        defer { if !silent { isLoading = false } }
        do {
            let list = try await api.list(token: token)
            self.videos = list.sorted { $0.createTime > $1.createTime }
            log.info("Loaded \(list.count) videos")
        } catch let err as AuthError {
            guard !silent else { return }  // poll failure: keep the current list, no flicker
            // A 暂不登录 / test session has no permission for resource analysis: the server
            // replies 401「无操作权限」. Surfacing that as a hard error with a "重试" button is
            // confusing (retry can never succeed). Match the web client, which silently
            // degrades a failed /video/list to an empty list, so the user just sees the
            // normal empty state. Genuine errors (network, 5xx) are still surfaced below.
            if case .server(let status, _) = err, status == 401 {
                log.info("video/list 401 (no permission); showing empty state")
                self.videos = []
                self.error = nil
            } else {
                error = err.errorDescription
            }
        } catch {
            guard !silent else { return }
            self.error = error.localizedDescription
        }
    }

    func delete(id: String) async {
        guard let token = tokenProvider(), !token.isEmpty else { return }
        guard let idx = videos.firstIndex(where: { $0.id == id }) else { return }
        let removed = videos.remove(at: idx)
        do {
            _ = try await api.operate(
                VideoOperationRequest(operation: .delete, id: id),
                token: token
            )
            log.info("Deleted video \(id, privacy: .public)")
        } catch let err as AuthError {
            videos.insert(removed, at: idx)
            videos.sort { $0.createTime > $1.createTime }
            error = err.errorDescription
        } catch {
            videos.insert(removed, at: idx)
            videos.sort { $0.createTime > $1.createTime }
            self.error = error.localizedDescription
        }
    }

    func insert(_ summary: VideoSummary) {
        if let idx = videos.firstIndex(where: { $0.id == summary.id }) {
            videos[idx] = summary
        } else {
            videos.insert(summary, at: 0)
        }
        videos.sort { $0.createTime > $1.createTime }
    }

    // MARK: - Add-video tasks (智云 import / 本地 upload) — foreground-continue

    /// One in-flight add-video task (a 智云 import or a local upload), surfaced as a banner on the
    /// list. The task is owned HERE — not by the add-video sheet — so the user can dismiss the
    /// sheet (返回) and the work keeps running while the app stays foreground. On success the video
    /// is inserted as 未开始分析; there is NO auto-analysis — the user picks 云端 / 本地 on the
    /// detail page. Both sources go through this same path, so the two flows are identical.
    struct VideoTaskState: Equatable, Identifiable {
        enum Kind: Equatable { case importing, uploading }
        enum Phase: Equatable { case running, done, failed(String) }
        let id = UUID()
        let kind: Kind
        let title: String
        var detail: String      // 导入中 / 上传中 / 合并中 / 创建中 …
        var percent: Int?       // nil → indeterminate (spinner, no bar)
        var phase: Phase
        var verb: String { kind == .importing ? "导入" : "上传" }
    }

    /// Tasks run concurrently — a 智云 import and any number of local uploads can be in flight at
    /// once; each has its own `Task` handle and its own row in the banner.
    @Published var videoTasks: [VideoTaskState] = []
    private var videoTaskHandles: [UUID: Task<Void, Never>] = [:]
    /// taskID → 智云导入的 import_id（仅 import 任务有）；取消时据此通知后端取消导入。
    private var zhiyunImportIDs: [UUID: String] = [:]

    func cancelVideoTask(_ id: UUID) {
        videoTaskHandles[id]?.cancel()
        // 智云导入：仅取消客户端 Task 不可靠（后端会继续下载并落库，视频随后仍出现在列表里），
        // 需显式通知后端写取消标记。本地上传无此问题（取消即停止分片，最终 create 不会发生）。
        if let importID = zhiyunImportIDs[id], let token = tokenProvider(), !token.isEmpty {
            Task { [api] in try? await api.cancelZhiyunImport(importID: importID, token: token) }
        }
        removeTask(id)
    }

    /// Dismiss a finished (done/failed) row; a running task is left alone.
    func dismissTaskBanner(_ id: UUID) {
        guard let task = videoTasks.first(where: { $0.id == id }) else { return }
        if case .running = task.phase { return }
        removeTask(id)
    }

    private func removeTask(_ id: UUID) {
        videoTasks.removeAll { $0.id == id }
        videoTaskHandles[id] = nil
        zhiyunImportIDs[id] = nil
    }

    private func mutateTask(_ id: UUID, _ change: (inout VideoTaskState) -> Void) {
        guard let idx = videoTasks.firstIndex(where: { $0.id == id }) else { return }
        change(&videoTasks[idx])
    }

    /// Shared completion: insert the new (unstarted) video, flash 完成, then auto-clear the row.
    private func finishVideoTask(_ taskID: UUID, videoID id: String, name: String) async {
        insert(VideoSummary(
            id: id,
            name: name,
            status: .unstarted,
            createTime: ISO8601DateFormatter().string(from: Date())
        ))
        mutateTask(taskID) { $0.detail = ""; $0.percent = 100; $0.phase = .done }
        await refresh(silent: true)
        try? await Task.sleep(nanoseconds: 2_000_000_000)
        if let task = videoTasks.first(where: { $0.id == taskID }), case .done = task.phase {
            removeTask(taskID)
        }
    }

    // MARK: 智云课堂 import

    func startZhiyunImport(_ course: ZhiyunCourse) {
        guard let token = tokenProvider(), !token.isEmpty else {
            videoTasks.append(VideoTaskState(kind: .importing, title: course.courseName, detail: "", percent: nil, phase: .failed("未登录")))
            return
        }
        // Match the name the server stores ("课程名 + 章节") so the row groups under its course.
        let displayName = [course.courseName, course.subTitle]
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
            .joined(separator: " ")

        let task = VideoTaskState(kind: .importing, title: displayName, detail: "导入中", percent: 0, phase: .running)
        let taskID = task.id
        // 本次导入标识：取消时据此通知后端写取消标记（UUID 在 iOS 原生可用，无安全上下文限制）
        let importID = UUID().uuidString
        zhiyunImportIDs[taskID] = importID
        videoTasks.append(task)
        videoTaskHandles[taskID] = Task { @MainActor [weak self] in
            guard let self else { return }
            defer { self.videoTaskHandles[taskID] = nil }
            do {
                var lastID: String?
                for try await event in self.api.importZhiyun(courseID: course.courseID, subID: course.subID, importID: importID, token: token) {
                    if Task.isCancelled { break }
                    switch event {
                    case .start(let id):
                        lastID = id
                    case .progress(let p):
                        self.mutateTask(taskID) { $0.percent = max(0, min(100, p)) }
                    case .error(let msg):
                        self.mutateTask(taskID) { $0.phase = .failed(msg) }
                        return
                    case .end(let endID):
                        guard let id = endID ?? lastID, !id.isEmpty else {
                            self.mutateTask(taskID) { $0.phase = .failed("导入完成但缺少视频 ID") }
                            return
                        }
                        await self.finishVideoTask(taskID, videoID: id, name: displayName)
                        return
                    }
                }
                self.mutateTask(taskID) { if case .running = $0.phase { $0.phase = .failed("导入提前结束") } }
            } catch is CancellationError {
                self.removeTask(taskID)
            } catch let err as AuthError {
                self.mutateTask(taskID) { $0.phase = .failed(err.errorDescription ?? "导入失败") }
            } catch {
                self.mutateTask(taskID) { $0.phase = .failed(error.localizedDescription) }
            }
        }
    }

    // MARK: 本地视频 upload (init → 分片上传 → finish → create)

    func startLocalUpload(fileURL: URL, name: String) {
        guard let token = tokenProvider(), !token.isEmpty else {
            videoTasks.append(VideoTaskState(kind: .uploading, title: name, detail: "", percent: nil, phase: .failed("未登录")))
            return
        }
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let displayName = trimmed.isEmpty ? "未命名视频" : trimmed

        let task = VideoTaskState(kind: .uploading, title: displayName, detail: "初始化中", percent: nil, phase: .running)
        let taskID = task.id
        videoTasks.append(task)
        videoTaskHandles[taskID] = Task { @MainActor [weak self] in
            guard let self else { return }
            defer { self.videoTaskHandles[taskID] = nil }

            let scopeOK = fileURL.startAccessingSecurityScopedResource()
            defer { if scopeOK { fileURL.stopAccessingSecurityScopedResource() } }

            let data: Data
            do {
                data = try Data(contentsOf: fileURL, options: [.mappedIfSafe])
            } catch {
                self.mutateTask(taskID) { $0.phase = .failed("读取视频失败：\(error.localizedDescription)") }
                return
            }

            let chunkSize = VideoAPI.chunkSize
            let chunks = max(1, (data.count + chunkSize - 1) / chunkSize)

            // init
            let uploadID: String
            do {
                uploadID = try await self.api.initUpload(totalChunks: chunks, token: token)
            } catch let err as AuthError {
                self.mutateTask(taskID) { $0.phase = .failed(err.errorDescription ?? "初始化失败") }; return
            } catch {
                self.mutateTask(taskID) { $0.phase = .failed(error.localizedDescription) }; return
            }

            // 分片上传 (sequential)
            self.mutateTask(taskID) { $0.detail = "上传中"; $0.percent = 0 }
            for index in 0..<chunks {
                if Task.isCancelled { self.removeTask(taskID); return }
                let start = index * chunkSize
                let end = min(start + chunkSize, data.count)
                let slice = data.subdata(in: start..<end)
                do {
                    try await self.api.uploadChunk(uploadID: uploadID, index: index, data: slice, filename: fileURL.lastPathComponent, token: token)
                } catch let err as AuthError {
                    self.mutateTask(taskID) { $0.phase = .failed(err.errorDescription ?? "分片 \(index) 上传失败") }; return
                } catch {
                    self.mutateTask(taskID) { $0.phase = .failed("分片 \(index) 上传失败：\(error.localizedDescription)") }; return
                }
                self.mutateTask(taskID) { $0.percent = Int(Double(index + 1) / Double(chunks) * 100) }
            }

            // finish (merge)
            self.mutateTask(taskID) { $0.detail = "合并中"; $0.percent = nil }
            let result: VideoAPI.UploadFinishResult
            do {
                result = try await self.api.finishUpload(uploadID: uploadID, token: token)
            } catch let err as AuthError {
                self.mutateTask(taskID) { $0.phase = .failed(err.errorDescription ?? "合并上传失败") }; return
            } catch {
                self.mutateTask(taskID) { $0.phase = .failed(error.localizedDescription) }; return
            }

            // create record (UNSTARTED — no auto-analysis)
            self.mutateTask(taskID) { $0.detail = "创建中" }
            do {
                let newID = try await self.api.operate(
                    VideoOperationRequest(operation: .create, name: displayName, path: result.videoPath, cover: result.coverPath),
                    token: token
                )
                await self.finishVideoTask(taskID, videoID: newID, name: displayName)
            } catch let err as AuthError {
                self.mutateTask(taskID) { $0.phase = .failed(err.errorDescription ?? "创建视频失败") }
            } catch {
                self.mutateTask(taskID) { $0.phase = .failed(error.localizedDescription) }
            }
        }
    }
}
