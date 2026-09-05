import SwiftUI
import MarkdownUI

struct ResourceDetailView: View {
    let resourceID: String
    let previewName: String
    let api: ResourceAPI
    let tokenProvider: () -> String?
    let onDeleted: (String) -> Void

    @State private var detail: ResourceDetail?
    @State private var isLoading: Bool = false
    @State private var error: String?
    @State private var pendingDelete: Bool = false
    @State private var deleteError: String?

    var body: some View {
        Group {
            if let detail {
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        header(for: detail)
                        Divider().padding(.vertical, 4)
                        if detail.content.isEmpty {
                            Text("（内容为空）")
                                .foregroundStyle(.secondary)
                                .font(.footnote)
                        } else {
                            Markdown(detail.content)
                                .markdownTheme(.chatAssistant)
                                .textSelection(.enabled)
                        }
                    }
                    .padding(16)
                }
            } else if isLoading {
                ProgressView("加载中…")
            } else if let error {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red).font(.system(size: 40))
                    Text("加载失败").font(.headline)
                    Text(error).font(.footnote).foregroundStyle(.secondary)
                    Button("重试") { Task { await load() } }
                        .buttonStyle(.borderedProminent)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
            } else {
                Color.clear
            }
        }
        .navigationTitle(detail?.name ?? previewName)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(role: .destructive) { pendingDelete = true } label: {
                    Image(systemName: "trash")
                }
                .disabled(detail == nil)
            }
        }
        .task { await load() }
        .confirmationDialog(
            "删除该资源",
            isPresented: $pendingDelete,
            titleVisibility: .visible
        ) {
            Button("删除", role: .destructive) {
                pendingDelete = false
                onDeleted(resourceID)
            }
            Button("取消", role: .cancel) { pendingDelete = false }
        } message: {
            Text("删除后将无法恢复，确定要删除该资源吗？")
        }
    }

    private func header(for detail: ResourceDetail) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Label(detail.resourceType.displayName, systemImage: detail.resourceType.iconName)
                    .labelStyle(.tight)
                    .font(.footnote)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.accentColor.opacity(0.12), in: Capsule())
                    .foregroundStyle(Color.accentColor)
                Text("\(detail.wordCount) 字")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            if let name = detail.relatedCourse?.name, !name.isEmpty {
                Text("关联课程：\(name)")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            HStack(spacing: 12) {
                if !detail.createTime.isEmpty {
                    Text("创建于 \(detail.createTime)")
                }
                if !detail.updateTime.isEmpty, detail.updateTime != detail.createTime {
                    Text("更新于 \(detail.updateTime)")
                }
            }
            .font(.caption)
            .foregroundStyle(.tertiary)
        }
    }

    private func load() async {
        guard let token = tokenProvider() else {
            error = "未登录"
            return
        }
        isLoading = true
        error = nil
        defer { isLoading = false }
        do {
            detail = try await api.detail(id: resourceID, token: token)
        } catch let err as AuthError {
            error = err.errorDescription
        } catch {
            self.error = error.localizedDescription
        }
    }
}
