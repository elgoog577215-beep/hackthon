import SwiftUI

struct ZhiyunImportView: View {
    let api: VideoAPI
    let tokenProvider: () -> String?
    /// Hand the chosen course up to the (persistent) list, which runs the import so it survives
    /// this sheet being dismissed. Progress then shows on the list, not here.
    let onImport: (ZhiyunCourse) -> Void

    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel: ZhiyunImportViewModel
    @State private var pendingImport: CourseSession?

    init(api: VideoAPI,
         tokenProvider: @escaping () -> String?,
         onImport: @escaping (ZhiyunCourse) -> Void) {
        self.api = api
        self.tokenProvider = tokenProvider
        self.onImport = onImport
        _viewModel = StateObject(wrappedValue: ZhiyunImportViewModel(
            api: api,
            tokenProvider: tokenProvider
        ))
    }

    var body: some View {
        Form {
            Section("筛选条件") {
                DatePicker("起始日期", selection: $viewModel.beginDate, displayedComponents: .date)
                DatePicker("结束日期", selection: $viewModel.endDate, displayedComponents: .date)
                TextField("课程名称（可选）", text: $viewModel.courseNameFilter)
            }
            Section {
                Button {
                    Task { await viewModel.searchCourses() }
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "magnifyingglass")
                        Text("查询课程")
                    }
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                }
                .buttonStyle(.borderedProminent)
                .disabled(isBusy)
            }
            phaseSection
        }
        .labelStyle(.tight)
        .navigationTitle("智云课堂")
        .navigationBarTitleDisplayMode(.inline)
        .navigationBarBackButtonHidden(true)
        .toolbar {
            if !isBusy {
                ToolbarItem(placement: .topBarLeading) {
                    Button("返回") { dismiss() }
                }
            }
        }
        .interactiveDismissDisabled(isBusy)
        .confirmationDialog(
            importTitle,
            isPresented: importBinding,
            titleVisibility: .visible,
            presenting: pendingImport
        ) { session in
            Button("导入") {
                let course = session.course
                pendingImport = nil
                Haptics.tap()
                // Hand off to the list and close this sheet — the import keeps running there.
                onImport(course)
            }
            Button("取消", role: .cancel) { pendingImport = nil }
        } message: { session in
            Text("章节：\(session.displayTitle)\n将开始下载并分析，可返回列表查看进度。确定导入吗？")
        }
    }

    private var importTitle: String {
        guard let session = pendingImport else { return "导入课程录像" }
        return "导入「\(session.course.courseName)」"
    }

    private var importBinding: Binding<Bool> {
        Binding(
            get: { pendingImport != nil },
            set: { if !$0 { pendingImport = nil } }
        )
    }

    @ViewBuilder
    private var phaseSection: some View {
        switch viewModel.phase {
        case .idle:
            EmptyView()
        case .searching:
            Section { HStack { ProgressView(); Text("正在查询课程…") } }
        case .picking(let courses):
            if courses.isEmpty {
                Section { Text("未查询到课程。").foregroundStyle(.secondary) }
            } else {
                ForEach(groupedByName(courses)) { group in
                    Section("\(group.name)（\(group.sessions.count)）") {
                        ForEach(group.sessions) { session in
                            Button {
                                pendingImport = session
                            } label: {
                                CourseRow(session: session)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
        case .failed(let msg):
            Section { ErrorBanner(text: msg) }
        }
    }

    // Only true while a course search is running. Import is owned by the list now, so picking a
    // course closes this sheet — there's no in-sheet import phase to block 返回 on.
    private var isBusy: Bool {
        switch viewModel.phase {
        case .searching: return true
        default: return false
        }
    }

    /// Groups sessions under their course name, preserving first-appearance order.
    /// 智云课堂 returns one entry per recording, so sessions sharing a date/节次 are
    /// numbered (录制 N) to keep otherwise-identical recordings tellable apart.
    private func groupedByName(_ courses: [ZhiyunCourse]) -> [CourseGroup] {
        var order: [String] = []
        var buckets: [String: [ZhiyunCourse]] = [:]
        for course in courses {
            if buckets[course.courseName] == nil { order.append(course.courseName) }
            buckets[course.courseName, default: []].append(course)
        }
        return order.map { name in
            let bucket = buckets[name] ?? []
            var totals: [String: Int] = [:]
            for course in bucket { totals[sessionLabel(course), default: 0] += 1 }
            var seen: [String: Int] = [:]
            let sessions = bucket.map { course -> CourseSession in
                let base = sessionLabel(course)
                guard (totals[base] ?? 0) > 1 else {
                    return CourseSession(course: course, displayTitle: base)
                }
                let index = (seen[base] ?? 0) + 1
                seen[base] = index
                return CourseSession(course: course, displayTitle: "\(base) · 录制 \(index)")
            }
            return CourseGroup(name: name, sessions: sessions)
        }
    }

    private func sessionLabel(_ course: ZhiyunCourse) -> String {
        course.subTitle.isEmpty ? course.classBegin : course.subTitle
    }
}

private struct CourseGroup: Identifiable {
    let name: String
    let sessions: [CourseSession]
    var id: String { name }
}

private struct CourseSession: Identifiable {
    let course: ZhiyunCourse
    let displayTitle: String
    var id: String { course.id }
}

private struct CourseRow: View {
    let session: CourseSession

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(session.displayTitle)
                .font(.subheadline)
                .lineLimit(2)
            HStack(spacing: 10) {
                if !session.course.teacherName.isEmpty {
                    Label(session.course.teacherName, systemImage: "person.fill")
                }
                if !session.course.classBegin.isEmpty {
                    Label(session.course.classBegin, systemImage: "calendar")
                }
            }
            .labelStyle(.tight)
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        .padding(.vertical, 2)
    }
}
