import SwiftUI
import AVKit

struct VideoAnalysisDetailView: View {
    /// The 总览 + 5-dimension tabs the report is split across.
    enum ReportTab: CaseIterable, Hashable {
        case overview, expression, design, knowledge, interaction, ideology
        var title: String {
            switch self {
            case .overview:    return "总览"
            case .expression:  return "教学表达"
            case .design:      return "教学设计"
            case .knowledge:   return "知识呈现"
            case .interaction: return "互动质量"
            case .ideology:    return "思政融合"
            }
        }
    }

    let videoID: String
    let previewName: String
    let api: VideoAPI
    let tokenProvider: () -> String?
    let onDeleted: (String) -> Void
    var onChanged: () -> Void = {}
    /// When set, the page renders this fixed detail and skips all networking/polling.
    /// Used by the DEBUG sample entry point to UI-test the report without a backend.
    var sampleDetail: VideoDetail? = nil

    @State private var detail: VideoDetail?
    @State private var isLoading: Bool = false
    @State private var error: String?
    @State private var pendingDelete: Bool = false
    @State private var analysisMethodPrompt: Bool = false
    @State private var analyzeError: String?
    @State private var pollTask: Task<Void, Never>?
    @State private var selectedTab: ReportTab = .overview

    var body: some View {
        Group {
            if let detail {
                loadedContent(for: detail)
            } else if isLoading {
                ProgressView("加载中…")
            } else if let error {
                errorView(error)
            } else {
                Color.clear
            }
        }
        .navigationTitle(detail?.name ?? previewName)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    Button {
                        Task { await reload() }
                    } label: {
                        Label("刷新", systemImage: "arrow.clockwise")
                    }
                    if let detail, detail.status != .waiting {
                        Button {
                            analysisMethodPrompt = true
                        } label: {
                            Label("开始/重新分析", systemImage: "wand.and.sparkles")
                        }
                    }
                    Button(role: .destructive) {
                        pendingDelete = true
                    } label: {
                        Label("删除", systemImage: "trash")
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                }
                .disabled(detail == nil)
            }
        }
        .task { await reload() }
        .onDisappear { pollTask?.cancel() }
        .confirmationDialog(
            "删除该视频",
            isPresented: $pendingDelete,
            titleVisibility: .visible
        ) {
            Button("删除", role: .destructive) {
                pendingDelete = false
                onDeleted(videoID)
            }
            Button("取消", role: .cancel) { pendingDelete = false }
        } message: {
            Text("删除后将无法恢复，确定要删除该视频吗？")
        }
        // 选择分析方式：mirrors the web `AnalysisMethodSelectModal` (云端/本地). The 开始分析 /
        // 开始-重新分析 entry points open this instead of analyzing directly.
        .confirmationDialog(
            "选择分析方式",
            isPresented: $analysisMethodPrompt,
            titleVisibility: .visible
        ) {
            Button("云端分析") {
                Task { await triggerAnalyze(mode: .cloud) }
            }
            Button("本地分析") {
                Task { await triggerAnalyze(mode: .local) }
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text("云端分析上传至云端处理，需等待平台；本地分析使用本地模型直接分析视频，不依赖第三方平台。")
        }
    }

    @ViewBuilder
    private func loadedContent(for detail: VideoDetail) -> some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16, pinnedViews: [.sectionHeaders]) {
                header(for: detail)
                videoPreview(for: detail)
                if let err = analyzeError {
                    ErrorBanner(text: err)
                }
                statusBanner(for: detail)
                reportSection(for: detail)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 16)
        }
        .refreshable { await reload(silent: true) }
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.red).font(.system(size: 40))
            Text("加载失败").font(.headline)
            Text(message).font(.footnote).foregroundStyle(.secondary)
            Button("重试") { Task { await load() } }
                .buttonStyle(.borderedProminent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    private func header(for detail: VideoDetail) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                HStack(spacing: 4) {
                    Image(systemName: detail.status.iconName)
                    Text(detail.status.displayLabel)
                }
                .font(.footnote)
                .padding(.horizontal, 10).padding(.vertical, 4)
                .background(statusBackground(detail.status), in: Capsule())
                .foregroundStyle(statusForeground(detail.status))
                if let dur = detail.analysisResult?.audioDuration, dur > 0 {
                    Text("视频时长：\(formatDuration(dur))")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            if !detail.path.isEmpty {
                Text(detail.path)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            HStack {
                if !detail.createTime.isEmpty {
                    Text("创建于 \(detail.createTime)")
                }
                if let start = detail.analysisStartTime, !start.isEmpty {
                    Text("开始分析 \(start)")
                }
            }
            .font(.caption)
            .foregroundStyle(.tertiary)
        }
    }

    @ViewBuilder
    private func statusBanner(for detail: VideoDetail) -> some View {
        let hasPartial = detail.analysisResult?.hasContent == true
        switch detail.status {
        case .waiting:
            HStack(spacing: 10) {
                ProgressView()
                Text(hasPartial ? "分析中，已生成部分结果，将持续更新…" : "分析中，请稍后…")
                    .foregroundStyle(.secondary)
            }
            .padding()
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 10))
        case .failed:
            ErrorBanner(text: hasPartial
                ? "分析未全部完成，以下为已生成的部分结果，可在右上角菜单中重新尝试分析。"
                : "分析失败，可在右上角菜单中重新尝试分析。")
        case .unstarted:
            VStack(alignment: .leading, spacing: 8) {
                Text("该视频尚未分析。")
                Button {
                    analysisMethodPrompt = true
                } label: {
                    Label("开始分析", systemImage: "wand.and.sparkles")
                        .foregroundStyle(.white)
                }
                .buttonStyle(.borderedProminent)
            }
        case .success:
            EmptyView()
        }
    }

    /// The report is split into 总览 + 5 dimension tabs. Only tabs with data are shown; the
    /// selected tab's cards render below a sticky segmented bar — keeping each view short.
    @ViewBuilder
    private func reportSection(for detail: VideoDetail) -> some View {
        if let result = detail.analysisResult, result.hasContent {
            let tabs = ReportTab.allCases.filter { tabHasContent($0, result) }
            let active = tabs.contains(selectedTab) ? selectedTab : (tabs.first ?? .overview)
            Section {
                VStack(alignment: .leading, spacing: 20) {
                    tabContent(active, result)
                }
                .padding(.top, 12)
                .frame(maxWidth: .infinity, alignment: .leading)
            } header: {
                reportTabBar(tabs: tabs, active: active)
            }
        } else if detail.status == .success {
            Text("暂无分析数据。").foregroundStyle(.secondary)
        }
    }

    /// Horizontally-scrollable segmented bar; pins to the top while the report scrolls.
    private func reportTabBar(tabs: [ReportTab], active: ReportTab) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(tabs, id: \.self) { tab in
                    let selected = tab == active
                    Button {
                        withAnimation(.easeInOut(duration: 0.18)) { selectedTab = tab }
                    } label: {
                        Text(tab.title)
                            .font(.subheadline.weight(selected ? .semibold : .regular))
                            .foregroundStyle(selected ? Color.white : Color.primary)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 7)
                            .background(selected ? Color.accentColor : Color(.secondarySystemBackground), in: Capsule())
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
        }
        // Match the page background so the bar blends in, with a hairline that only reads
        // once it pins over scrolling content (avoids the abrupt floating-strip look).
        .background(
            Color(.systemBackground)
                .overlay(alignment: .bottom) { Divider() }
        )
        .padding(.horizontal, -16)
    }

    @ViewBuilder
    private func tabContent(_ tab: ReportTab, _ result: VideoAnalysisResult) -> some View {
        switch tab {
        case .overview:    overviewContent(result)
        case .expression:  expressionContent(result)
        case .design:      designContent(result)
        case .knowledge:   knowledgeContent(result)
        case .interaction: interactionContent(result)
        case .ideology:    ideologyContent(result)
        }
    }

    private func tabHasContent(_ tab: ReportTab, _ r: VideoAnalysisResult) -> Bool {
        switch tab {
        case .overview:    return !r.radarAxes.isEmpty || r.overallScore != nil || r.aiSummary?.isEmpty == false || !r.aiSuggestions.isEmpty
        case .expression:  return r.speechRate != nil || r.volume != nil || !r.fillerWords.isEmpty
        case .design:      return !r.typeDistribution.isEmpty || r.introAnalysis != nil || r.conclusionAnalysis != nil || !r.infoDensity.isEmpty || !r.designSegments.isEmpty
        case .knowledge:   return !r.wordCloud.isEmpty || !r.knowledgeTree.isEmpty
        case .interaction: return !r.whSlices.isEmpty || !r.typeStatistics.isEmpty || !r.interactionEvents.isEmpty
        case .ideology:    return !r.ideologyEvents.isEmpty
        }
    }

    // MARK: - 总览

    @ViewBuilder
    private func overviewContent(_ result: VideoAnalysisResult) -> some View {
        if !result.radarAxes.isEmpty {
            section(title: "整体评估概览", systemImage: "chart.xyaxis.line", accessory: {
                if let score = result.overallScore { scoreBadge(score) }
            }) {
                RadarChartView(axes: result.radarAxes)
            }
        }
        if let summary = result.aiSummary, !summary.isEmpty {
            section(title: "AI 总评摘要", systemImage: "text.quote") {
                Text(summary)
                    .font(.footnote)
                    .lineSpacing(3)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        if !result.aiSuggestions.isEmpty {
            section(title: "总体改进建议", systemImage: "lightbulb") {
                suggestionList(result.aiSuggestions)
            }
        }
    }

    private func suggestionList(_ lines: [String]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(lines.enumerated()), id: \.offset) { index, line in
                HStack(alignment: .top, spacing: 6) {
                    Text("\(index + 1).")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(Color.accentColor)
                    Text(line)
                        .font(.footnote)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    // MARK: - 教学表达

    // MARK: - 教学表达

    @ViewBuilder
    private func expressionContent(_ result: VideoAnalysisResult) -> some View {
        if let speech = result.speechRate {
            section(title: "语速分析", systemImage: "speedometer") {
                MetricLineChart(title: "语速变化趋势 (CPM)", samples: speech.samples, unit: "CPM",
                                totalDuration: speech.totalDuration,
                                statsAvg: speech.avg, statsMax: speech.max, statsMin: speech.min)
            }
        }
        if let volume = result.volume {
            section(title: "音量分析", systemImage: "speaker.wave.2") {
                MetricLineChart(title: "音量变化趋势 (dB)", samples: volume.samples, unit: "dB",
                                totalDuration: volume.totalDuration,
                                statsAvg: volume.avg, statsMax: volume.max, statsMin: volume.min)
            }
        }
        if !result.fillerWords.isEmpty {
            section(title: "语言精炼度", systemImage: "text.badge.checkmark") {
                FillerWordsView(words: result.fillerWords, ratio: result.fillerRatio, count: result.fillerCount)
            }
        }
    }

    // MARK: - 教学设计

    @ViewBuilder
    private func designContent(_ result: VideoAnalysisResult) -> some View {
        if !result.typeDistribution.isEmpty {
            section(title: "课堂环节占比", systemImage: "chart.pie") {
                DonutChartView(slices: result.typeDistribution)
            }
        }
        if result.introAnalysis != nil || result.conclusionAnalysis != nil {
            section(title: "导入与总结环节分析", systemImage: "flag.checkered") {
                VStack(alignment: .leading, spacing: 10) {
                    if let intro = result.introAnalysis {
                        PhaseAnalysisCard(title: "导入环节", analysis: intro)
                    }
                    if let conclusion = result.conclusionAnalysis {
                        PhaseAnalysisCard(title: "总结环节", analysis: conclusion)
                    }
                }
            }
        }
        if !result.infoDensity.isEmpty {
            section(title: "信息密度曲线", systemImage: "waveform.path.ecg") {
                MetricLineChart(title: "信息密度", samples: result.infoDensity, fractionDigits: 2)
            }
        }
        if !result.designSegments.isEmpty {
            section(title: "教学环节总结", systemImage: "list.bullet.rectangle") {
                designSegmentsPreview(result.designSegments)
            }
        }
    }

    @ViewBuilder
    private func designSegmentsPreview(_ segments: [TeachSegment]) -> some View {
        let previewSegments = Array(segments.prefix(3))
        VStack(alignment: .leading, spacing: 10) {
            TeachTimelineView(sections: [TeachSummarySection(summary: "", segments: previewSegments)], contentLineLimit: 2)
            if segments.count > previewSegments.count {
                NavigationLink {
                    TeachSummaryFullView(sections: [TeachSummarySection(summary: "", segments: segments)])
                } label: {
                    expandLabel("查看完整教学环节（共 \(segments.count) 个）")
                }
            }
        }
    }

    // MARK: - 知识呈现

    // MARK: - 知识呈现

    @ViewBuilder
    private func knowledgeContent(_ result: VideoAnalysisResult) -> some View {
        if !result.knowledgeTree.isEmpty {
            section(title: "知识点分布", systemImage: "list.bullet.indent") {
                knowledgeTreePreview(result.knowledgeTree)
            }
        }
        if !result.wordCloud.isEmpty {
            section(title: "高频关键词", systemImage: "tag") {
                WordCloudView(words: result.wordCloud.map { ($0.word, $0.weight) })
            }
        }
    }

    @ViewBuilder
    private func knowledgeTreePreview(_ nodes: [KnowledgeNode]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            KnowledgeTreeView(nodes: Array(nodes.prefix(5)), maxDepth: 0)
            NavigationLink {
                KnowledgeTreeFullView(nodes: nodes)
            } label: {
                expandLabel("查看完整知识点分布（共 \(nodes.count) 个主题）")
            }
        }
    }

    // MARK: - 互动质量

    // MARK: - 互动质量

    @ViewBuilder
    private func interactionContent(_ result: VideoAnalysisResult) -> some View {
        if !result.whSlices.isEmpty {
            section(title: "五何分布", systemImage: "bubble.left.and.bubble.right") {
                DonutChartView(slices: result.whSlices)
            }
        }
        if !result.typeStatistics.isEmpty {
            section(title: "互动类型统计", systemImage: "chart.bar") {
                DonutChartView(slices: result.typeStatistics)
            }
        }
        if !result.interactionEvents.isEmpty {
            section(title: "互动事件时间轴", systemImage: "clock") {
                interactionTimelinePreview(result.interactionEvents)
            }
        }
    }

    @ViewBuilder
    private func interactionTimelinePreview(_ events: [InteractionEvent]) -> some View {
        let previewEvents = Array(events.prefix(3))
        VStack(alignment: .leading, spacing: 10) {
            InteractionTimelineView(events: previewEvents)
            if events.count > previewEvents.count {
                NavigationLink {
                    InteractionTimelineFullView(events: events)
                } label: {
                    expandLabel("查看完整互动事件时间轴（共 \(events.count) 条）")
                }
            }
        }
    }

    // MARK: - 思政融合

    // MARK: - 思政融合

    @ViewBuilder
    private func ideologyContent(_ result: VideoAnalysisResult) -> some View {
        section(title: "思政事件", systemImage: "heart.text.square") {
            VStack(alignment: .leading, spacing: 10) {
                ForEach(result.ideologyEvents) { event in
                    IdeologyEventCard(event: event)
                }
            }
        }
    }

    private func expandLabel(_ text: String) -> some View {
        HStack(spacing: 4) {
            Text(text)
            Image(systemName: "chevron.right").font(.caption2)
        }
        .font(.caption.weight(.medium))
        .foregroundStyle(Color.accentColor)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, 2)
    }

    private func groupTitle(_ text: String) -> some View {
        Text(text)
            .font(.title3.weight(.semibold))
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private func videoPreview(for detail: VideoDetail) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            groupTitle("原视频")
            if let url = videoURL(for: detail.path) {
                VideoPreviewPlayer(url: url)
            } else {
                ZStack {
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(Color(.secondarySystemBackground))
                    VStack(spacing: 6) {
                        Image(systemName: "play.rectangle")
                            .font(.system(size: 40))
                            .foregroundStyle(.tertiary)
                        Text("视频播放区").font(.footnote).foregroundStyle(.secondary)
                    }
                }
                .frame(height: 210)
            }
            if !detail.name.isEmpty {
                Text(detail.name).font(.footnote).foregroundStyle(.secondary)
            }
        }
    }

    /// Builds a playable URL from the stored path. The file is always served from the
    /// unauthenticated `/static/` mount (requesting it under the API base routes through
    /// nginx to that mount). Mirrors the web's `resolveVideoMediaUrl`, but also tolerates
    /// the malformed paths the local-upload flow can store — e.g. a server-local prefix
    /// and a doubled slash like `/src//static/videos/…` — by resolving to the `/static/`
    /// segment regardless of any junk before it.
    private func videoURL(for rawPath: String) -> URL? {
        let raw = rawPath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !raw.isEmpty else { return nil }
        if raw.hasPrefix("http://") || raw.hasPrefix("https://") { return URL(string: raw) }
        var pathPart = raw
        if let range = pathPart.range(of: "/static/", options: .backwards) {
            // Drop anything before the static mount (handles "/src//static/…").
            pathPart = String(pathPart[range.lowerBound...])
        } else if let range = pathPart.range(of: "uploads/") {
            pathPart = "/static/" + pathPart[range.upperBound...]
        }
        if !pathPart.hasPrefix("/") { pathPart = "/" + pathPart }
        // Collapse any accidental doubled slashes in the path portion.
        while pathPart.contains("//") { pathPart = pathPart.replacingOccurrences(of: "//", with: "/") }
        let base = AuthConfig.default.apiBaseURL.absoluteString
        let baseTrimmed = base.hasSuffix("/") ? String(base.dropLast()) : base
        return URL(string: baseTrimmed + pathPart)
    }

    @ViewBuilder
    private func section<Content: View, Accessory: View>(
        title: String,
        systemImage: String,
        @ViewBuilder accessory: () -> Accessory = { EmptyView() },
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .center) {
                Label(title, systemImage: systemImage)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Color.accentColor)
                    .layoutPriority(1)
                Spacer(minLength: 8)
                accessory()
            }
            content()
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    /// 综合评分 — overall score badge (the V2 `综合得分` entry from radar_data).
    private func scoreBadge(_ score: Int) -> some View {
        Text("综合评分 \(score)/100")
            .font(.caption.weight(.semibold))
            .foregroundStyle(Color.accentColor)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Color.accentColor.opacity(0.12), in: Capsule())
    }

    private func reload(silent: Bool = false) async {
        await load(silent: silent)
        schedulePolling()
    }

    private func load(silent: Bool = false) async {
        if let sampleDetail {
            detail = sampleDetail
            error = nil
            return
        }
        guard let token = tokenProvider() else {
            if !silent { error = "未登录" }
            return
        }
        if !silent { isLoading = true }
        error = nil
        defer { if !silent { isLoading = false } }
        do {
            detail = try await api.detail(id: videoID, token: token)
        } catch let err as AuthError {
            if !silent { error = err.errorDescription }
        } catch {
            if !silent { self.error = error.localizedDescription }
        }
    }

    /// While the server reports WAITING, re-fetch every few seconds. Each fetch makes the
    /// backend poll chaoxing and persist the next slice of results, so partial results
    /// stream in (transcript → knowledge → summary …) without manual refresh.
    private func schedulePolling() {
        pollTask?.cancel()
        guard sampleDetail == nil, detail?.status == .waiting else { return }
        pollTask = Task { @MainActor in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 4_000_000_000)
                if Task.isCancelled { return }
                await load(silent: true)
                if detail?.status != .waiting {
                    onChanged()
                    return
                }
            }
        }
    }

    private func triggerAnalyze(mode: AnalysisMode) async {
        analyzeError = nil
        guard let token = tokenProvider() else {
            analyzeError = "未登录"
            return
        }
        do {
            try await api.analyze(id: videoID, mode: mode, token: token)
            await reload()
            onChanged()
        } catch let err as AuthError {
            analyzeError = err.errorDescription
        } catch {
            analyzeError = error.localizedDescription
        }
    }

    private func formatDuration(_ seconds: Double) -> String {
        let total = Int(seconds)
        let h = total / 3600
        let m = (total % 3600) / 60
        let s = total % 60
        if h > 0 {
            return String(format: "%d:%02d:%02d", h, m, s)
        }
        return String(format: "%d:%02d", m, s)
    }

    private func statusBackground(_ status: VideoStatus) -> Color {
        switch status {
        case .unstarted: return Color.gray.opacity(0.15)
        case .waiting:   return Color.orange.opacity(0.18)
        case .success:   return Color.green.opacity(0.18)
        case .failed:    return Color.red.opacity(0.18)
        }
    }
    private func statusForeground(_ status: VideoStatus) -> Color {
        switch status {
        case .unstarted: return .secondary
        case .waiting:   return .orange
        case .success:   return .green
        case .failed:    return .red
        }
    }
}

struct ErrorBanner: View {
    let text: String
    var body: some View {
        Label(text, systemImage: "exclamationmark.triangle.fill")
            .font(.footnote)
            .foregroundStyle(.red)
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.red.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
    }
}

private struct VideoPreviewPlayer: View {
    @State private var player: AVPlayer

    init(url: URL) {
        _player = State(initialValue: AVPlayer(url: url))
    }

    var body: some View {
        VideoPlayer(player: player)
            .frame(height: 210)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .onDisappear { player.pause() }
    }
}
