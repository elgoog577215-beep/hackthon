import SwiftUI

struct ResourceListView: View {
    @EnvironmentObject private var appState: AppState
    @StateObject private var viewModel: ResourceListViewModel
    @State private var path: [ResourceRoute] = []
    @State private var pendingDelete: ResourceSummary?
    @State private var newSheetShown: Bool = false

    init(viewModel: ResourceListViewModel) {
        _viewModel = StateObject(wrappedValue: viewModel)
    }

    var body: some View {
        NavigationStack(path: $path) {
            VStack(spacing: 0) {
                filterBar
                content
            }
            .navigationTitle("资源分析")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        newSheetShown = true
                    } label: {
                        Image(systemName: "plus.circle.fill")
                    }
                }
            }
            .refreshable {
                await viewModel.refresh()
            }
            .task {
                if viewModel.resources.isEmpty {
                    await viewModel.refresh()
                }
            }
            .sheet(isPresented: $newSheetShown) {
                OutlineFormView(
                    api: makeAPI(),
                    tokenProvider: tokenProvider(),
                    onSaved: { summary in
                        viewModel.insert(summary)
                        newSheetShown = false
                    }
                )
            }
            .navigationDestination(for: ResourceRoute.self) { route in
                switch route {
                case .detail(let id, let preview):
                    ResourceDetailView(
                        resourceID: id,
                        previewName: preview,
                        api: makeAPI(),
                        tokenProvider: tokenProvider(),
                        onDeleted: { deletedID in
                            Task { await viewModel.delete(id: deletedID) }
                            path.removeAll()
                        }
                    )
                }
            }
        }
    }

    private var filterBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                FilterChip(label: "全部",
                           isSelected: viewModel.filterType == nil) {
                    viewModel.filterType = nil
                    Task { await viewModel.refresh() }
                }
                ForEach(ResourceType.allCases) { type in
                    FilterChip(label: type.displayName,
                               systemImage: type.iconName,
                               isSelected: viewModel.filterType == type) {
                        viewModel.filterType = (viewModel.filterType == type) ? nil : type
                        Task { await viewModel.refresh() }
                    }
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
        }
        .background(Color(.secondarySystemBackground))
    }

    @ViewBuilder
    private var content: some View {
        if let errorMessage = viewModel.error, viewModel.resources.isEmpty {
            errorState(errorMessage)
        } else if viewModel.resources.isEmpty && !viewModel.isLoading {
            emptyState
        } else {
            list
        }
    }

    private var list: some View {
        List {
            ForEach(viewModel.resources) { resource in
                NavigationLink(value: ResourceRoute.detail(id: resource.id, previewName: resource.name)) {
                    ResourceRow(resource: resource)
                }
                .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                    Button(role: .destructive) {
                        pendingDelete = resource
                    } label: {
                        Label("删除", systemImage: "trash")
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
        ) { resource in
            Button("删除", role: .destructive) {
                let id = resource.id
                pendingDelete = nil
                Task { await viewModel.delete(id: id) }
            }
            Button("取消", role: .cancel) { pendingDelete = nil }
        } message: { _ in
            Text("删除后将无法恢复，确定要删除该资源吗？")
        }
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "tray")
                .font(.system(size: 56))
                .foregroundStyle(.tertiary)
            Text("暂无资源")
                .font(.headline)
            Text("点击右上角的 + 生成新的教学资源")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    private func errorState(_ text: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 44))
                .foregroundStyle(.red)
            Text("加载资源失败").font(.headline)
            Text(text)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
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
        return "删除该资源"
    }

    private var deleteBinding: Binding<Bool> {
        Binding(
            get: { pendingDelete != nil },
            set: { if !$0 { pendingDelete = nil } }
        )
    }

    private func makeAPI() -> ResourceAPI {
        ResourceAPI(baseURL: AuthConfig.default.apiBaseURL)
    }

    private func tokenProvider() -> () -> String? {
        let s = appState
        return {
            if case .signedIn(let session) = s.phase { return session.accessToken }
            return nil
        }
    }
}

enum ResourceRoute: Hashable {
    case detail(id: String, previewName: String)
}

private struct ResourceRow: View {
    let resource: ResourceSummary

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: resource.resourceType.iconName)
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(Color.accentColor)
                .frame(width: 36, height: 36)
                .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            VStack(alignment: .leading, spacing: 5) {
                Text(resource.name)
                    .font(.body.weight(.medium))
                    .lineLimit(2)
                HStack(spacing: 8) {
                    Text(resource.resourceType.displayName)
                        .font(.caption)
                        .foregroundStyle(Color.accentColor)
                    Text("·").foregroundStyle(.tertiary)
                    Text("\(resource.wordCount) 字")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let name = resource.relatedCourse?.name, !name.isEmpty {
                        Text("·").foregroundStyle(.tertiary)
                        Text(name)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
                Text(resource.updateTime.isEmpty ? resource.createTime : resource.updateTime)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 6)
    }
}

private struct FilterChip: View {
    let label: String
    var systemImage: String? = nil
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                if let systemImage {
                    Image(systemName: systemImage).font(.system(size: 12))
                }
                Text(label).font(.subheadline)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(isSelected ? Color.accentColor : Color(.systemBackground),
                        in: Capsule())
            .foregroundStyle(isSelected ? Color.white : Color.primary)
            .overlay(
                Capsule().stroke(isSelected ? Color.clear : Color.gray.opacity(0.3), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}
