import SwiftUI

struct VideoAnalysisListView: View {
    @EnvironmentObject private var appState: AppState
    @StateObject private var viewModel: VideoListViewModel
    @State private var path: [VideoRoute] = []
    @State private var pendingDelete: VideoSummary?
    @State private var newSheetShown: Bool = false

    init(viewModel: VideoListViewModel) {
        _viewModel = StateObject(wrappedValue: viewModel)
    }

    var body: some View {
        NavigationStack(path: $path) {
            content
                .navigationTitle("资源分析")
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button {
                            newSheetShown = true
                        } label: {
                            Image(systemName: "plus.circle.fill")
                        }
                    }
                    #if DEBUG
                    // Opens the analysis detail page with a bundled sample for UI testing.
                    ToolbarItem(placement: .topBarLeading) {
                        Button {
                            path.append(.sampleDetail)
                        } label: {
                            Image(systemName: "ladybug.fill")
                        }
                    }
                    #endif
                }
                .refreshable { await viewModel.refresh() }
                .task {
                    await viewModel.refresh()
                    // Auto-refresh: while any video is 分析中 (WAITING), re-fetch every 4s so its
                    // status flips to 已完成 / 分析失败 and the list count stays current — no manual
                    // pull needed. Idles (no network) once nothing is analyzing. Cancelled when the
                    // view goes away.
                    while !Task.isCancelled {
                        try? await Task.sleep(nanoseconds: 4_000_000_000)
                        if Task.isCancelled { break }
                        if viewModel.hasAnalyzingVideos {
                            await viewModel.refresh(silent: true)
                        }
                    }
                }
                // Pinned at the BOTTOM (above the tab bar). A top inset collides with / hides the
                // large navigation title under iOS 26's title layout.
                .safeAreaInset(edge: .bottom) { taskBanner }
                .sheet(isPresented: $newSheetShown) {
                    // Both add-video flows run on the (persistent) list VM and close the sheet, so
                    // they keep going while the app is foreground; progress shows in the banner.
                    NewVideoAnalysisView(
                        api: makeAPI(),
                        tokenProvider: tokenProvider(),
                        onZhiyunImport: { course in
                            viewModel.startZhiyunImport(course)
                            newSheetShown = false
                        },
                        onUpload: { url, name in
                            viewModel.startLocalUpload(fileURL: url, name: name)
                            newSheetShown = false
                        }
                    )
                }
                .navigationDestination(for: VideoRoute.self) { route in
                    switch route {
                    case .detail(let id, let preview):
                        VideoAnalysisDetailView(
                            videoID: id,
                            previewName: preview,
                            api: makeAPI(),
                            tokenProvider: tokenProvider(),
                            onDeleted: { deletedID in
                                Task { await viewModel.delete(id: deletedID) }
                                path.removeAll()
                            },
                            onChanged: {
                                Task { await viewModel.refresh() }
                            }
                        )
                    #if DEBUG
                    case .sampleDetail:
                        VideoAnalysisDetailView(
                            videoID: "sample",
                            previewName: "测试样例",
                            api: makeAPI(),
                            tokenProvider: tokenProvider(),
                            onDeleted: { _ in path.removeAll() },
                            sampleDetail: .sample
                        )
                    #endif
                    }
                }
        }
    }

    @ViewBuilder
    private var content: some View {
        if let errorMessage = viewModel.error, viewModel.videos.isEmpty {
            errorState(errorMessage)
        } else if viewModel.videos.isEmpty && !viewModel.isLoading {
            emptyState
        } else {
            list
        }
    }

    private var list: some View {
        List {
            ForEach(groupedByCourse(viewModel.videos)) { group in
                Section("\(group.name)（\(group.videos.count)）") {
                    ForEach(group.videos) { video in
                        videoLink(video, title: sessionTitle(for: video, course: group.name))
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
        .confirmationDialog(
            deleteTitle,
            isPresented: deleteBinding,
            titleVisibility: .visible,
            presenting: pendingDelete
        ) { video in
            Button("删除", role: .destructive) {
                let id = video.id
                pendingDelete = nil
                Haptics.notify(.success)
                Task { await viewModel.delete(id: id) }
            }
            Button("取消", role: .cancel) { pendingDelete = nil }
        } message: { _ in
            Text("删除后将无法恢复，确定要删除该视频吗？")
        }
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "video.badge.waveform")
                .font(.system(size: 56))
                .foregroundStyle(.tertiary)
            Text("暂无视频").font(.headline)
            Text("点击右上角的 + 添加智云课堂或本地视频")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    private func errorState(_ text: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 44)).foregroundStyle(.red)
            Text("加载视频失败").font(.headline)
            Text(text).font(.footnote).foregroundStyle(.secondary).multilineTextAlignment(.center)
            Button("重试") { Task { await viewModel.refresh() } }
                .buttonStyle(.borderedProminent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    private var deleteTitle: String {
        if let name = pendingDelete?.name, !name.isEmpty {
            return "删除「\(name)」"
        }
        return "删除该视频"
    }

    private var deleteBinding: Binding<Bool> {
        Binding(
            get: { pendingDelete != nil },
            set: { if !$0 { pendingDelete = nil } }
        )
    }

    private func videoLink(_ video: VideoSummary, title: String) -> some View {
        NavigationLink(value: VideoRoute.detail(id: video.id, previewName: video.name)) {
            VideoRow(video: video, title: title)
        }
        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
            // Plain button tinted red (not role: .destructive) so the List doesn't play its
            // row-removal animation on tap — we only open a confirmation dialog here.
            Button {
                pendingDelete = video
            } label: {
                Label("删除", systemImage: "trash")
            }
            .tint(.red)
        }
    }

    /// Groups videos by course name (derived from the zhiyun-style "课程名 日期 第X-Y节"
    /// naming), bucketing date-less local uploads under 本地视频. Preserves order.
    private func groupedByCourse(_ videos: [VideoSummary]) -> [VideoGroup] {
        var order: [String] = []
        var buckets: [String: [VideoSummary]] = [:]
        for video in videos {
            let key = courseName(from: video.name)
            if buckets[key] == nil { order.append(key) }
            buckets[key, default: []].append(video)
        }
        return order.map { VideoGroup(name: $0, videos: buckets[$0] ?? []) }
    }

    private func courseName(from name: String) -> String {
        if let range = name.range(of: "\\s*\\d{4}-\\d{2}-\\d{2}.*$", options: .regularExpression) {
            let prefix = String(name[..<range.lowerBound]).trimmingCharacters(in: .whitespaces)
            if !prefix.isEmpty { return prefix }
        }
        return "本地视频"
    }

    /// Row title within a course group: the session/date suffix, or the full name when it isn't a course session.
    private func sessionTitle(for video: VideoSummary, course: String) -> String {
        let name = video.name.trimmingCharacters(in: .whitespaces)
        if name != course, name.hasPrefix(course) {
            let remainder = String(name.dropFirst(course.count)).trimmingCharacters(in: .whitespaces)
            if !remainder.isEmpty { return remainder }
        }
        return name.isEmpty ? "未命名视频" : name
    }

    /// In-flight add-video tasks (智云 import / 本地 upload), pinned above the list. Tasks run on
    /// the (persistent) view model, so they keep going after the add-video sheet is dismissed — as
    /// long as the app stays foreground. Several can run concurrently, one row each. Empty (zero
    /// height) when nothing is in flight.
    @ViewBuilder
    private var taskBanner: some View {
        if !viewModel.videoTasks.isEmpty {
            VStack(spacing: 0) {
                // Divider before each row → a hairline separating the banner from the list above,
                // plus separators between rows (no trailing divider against the tab bar).
                ForEach(viewModel.videoTasks) { task in
                    Divider()
                    taskRow(task)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .background(.regularMaterial)
        }
    }

    @ViewBuilder
    private func taskRow(_ task: VideoListViewModel.VideoTaskState) -> some View {
        switch task.phase {
        case .running:
            HStack(spacing: 12) {
                ProgressView().controlSize(.small)
                VStack(alignment: .leading, spacing: 4) {
                    Text("正在\(task.verb)「\(task.title)」\(task.detail.isEmpty ? "" : " · \(task.detail)")")
                        .font(.footnote).lineLimit(1)
                    if let percent = task.percent {
                        ProgressView(value: Double(percent) / 100)
                    } else {
                        ProgressView().progressViewStyle(.linear)  // indeterminate
                    }
                }
                if let percent = task.percent {
                    Text("\(percent)%").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                }
                Button("取消") { viewModel.cancelVideoTask(task.id) }
                    .font(.caption).foregroundStyle(.red)
            }
        case .done:
            HStack(spacing: 8) {
                Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                Text("「\(task.title)」已\(task.verb)，可在详情页开始分析").font(.footnote).lineLimit(1)
                Spacer(minLength: 0)
            }
        case .failed(let msg):
            HStack(spacing: 8) {
                Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.red)
                VStack(alignment: .leading, spacing: 2) {
                    Text("「\(task.title)」\(task.verb)失败").font(.footnote)
                    Text(msg).font(.caption2).foregroundStyle(.secondary).lineLimit(2)
                }
                Spacer(minLength: 0)
                Button("关闭") { viewModel.dismissTaskBanner(task.id) }.font(.caption)
            }
        }
    }

    private func makeAPI() -> VideoAPI {
        VideoAPI(baseURL: AuthConfig.default.apiBaseURL)
    }

    private func tokenProvider() -> () -> String? {
        let s = appState
        return {
            if case .signedIn(let session) = s.phase { return session.accessToken }
            return nil
        }
    }
}

enum VideoRoute: Hashable {
    case detail(id: String, previewName: String)
    #if DEBUG
    case sampleDetail
    #endif
}

private struct VideoGroup: Identifiable {
    let name: String
    let videos: [VideoSummary]
    var id: String { name }
}

private struct VideoRow: View {
    let video: VideoSummary
    var title: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "play.rectangle.fill")
                .font(.system(size: 24))
                .foregroundStyle(Color.accentColor)
                .frame(width: 44, height: 44)
                .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            VStack(alignment: .leading, spacing: 5) {
                Text(title).font(.body.weight(.medium)).lineLimit(2)
                HStack(spacing: 4) {
                    Image(systemName: video.status.iconName)
                    Text(video.status.displayLabel)
                    if let eta = etaText {
                        Text("· \(eta)").foregroundStyle(.secondary)
                    }
                }
                .font(.caption)
                .foregroundStyle(statusColor(for: video.status))
                Text(ServerDate.relative(video.createTime)).font(.caption2).foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 6)
    }

    /// 本地分析「分析中」的预计剩余时间文案（用后端 estimated_seconds，含排队+并发+时长；
    /// 列表每 4s 自动刷新带回最新值，故直接展示即可。云端分析为 nil → 不显示。）
    private var etaText: String? {
        guard video.status == .waiting, let secs = video.estimatedSeconds, secs > 0 else { return nil }
        if secs <= 30 { return "即将完成" }
        let totalMin = max(1, Int((Double(secs) / 60.0).rounded(.up)))
        let h = totalMin / 60
        let m = totalMin % 60
        let part: String
        if h > 0 && m > 0 { part = "\(h)小时\(m)分钟" }
        else if h > 0 { part = "\(h)小时" }
        else { part = "\(m)分钟" }
        return "预计剩余约\(part)"
    }

    private func statusColor(for status: VideoStatus) -> Color {
        switch status {
        case .unstarted: return .secondary
        case .waiting:   return .orange
        case .success:   return .green
        case .failed:    return .red
        }
    }
}
