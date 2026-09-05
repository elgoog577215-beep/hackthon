import SwiftUI

struct SessionListView: View {
    @EnvironmentObject private var appState: AppState
    @StateObject private var viewModel: SessionListViewModel
    @State private var path: [ChatRoute] = []
    @State private var pendingDelete: ChatSession?

    init(viewModel: SessionListViewModel) {
        _viewModel = StateObject(wrappedValue: viewModel)
    }

    var body: some View {
        NavigationStack(path: $path) {
            content
                .navigationTitle("对话")
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button {
                            path.append(.new)
                        } label: {
                            Image(systemName: "square.and.pencil")
                        }
                    }
                }
                .refreshable {
                    await viewModel.refresh()
                }
                .task {
                    if viewModel.sessions.isEmpty {
                        await viewModel.refresh()
                    }
                }
                .navigationDestination(for: ChatRoute.self) { route in
                    ChatView(viewModel: makeChatViewModel(for: route)) {
                        Task { await viewModel.refresh() }
                    }
                }
        }
    }

    @ViewBuilder
    private var content: some View {
        if let errorMessage = viewModel.error, viewModel.sessions.isEmpty {
            errorState(errorMessage)
        } else if viewModel.sessions.isEmpty && !viewModel.isLoading {
            emptyState
        } else {
            list
        }
    }

    private var list: some View {
        List {
            ForEach(viewModel.sessions) { session in
                NavigationLink(value: ChatRoute.existing(id: session.id)) {
                    SessionRow(session: session)
                }
                .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                    // Plain button tinted red (not role: .destructive): a destructive swipe
                    // button makes the List play its row-removal animation on tap, so the row
                    // collapses then springs back when we only open a confirmation dialog.
                    Button {
                        pendingDelete = session
                    } label: {
                        Label("删除", systemImage: "trash")
                    }
                    .tint(.red)
                }
            }
        }
        .listStyle(.insetGrouped)
        .confirmationDialog(
            confirmationTitle,
            isPresented: confirmationBinding,
            titleVisibility: .visible,
            presenting: pendingDelete
        ) { session in
            Button("删除", role: .destructive) {
                let id = session.id
                pendingDelete = nil
                Haptics.notify(.success)
                Task { await viewModel.delete(id: id) }
            }
            Button("取消", role: .cancel) {
                pendingDelete = nil
            }
        } message: { _ in
            Text("删除后将无法恢复，确定要删除该对话吗？")
        }
    }

    private var confirmationTitle: String {
        if let title = pendingDelete?.displayTitle, !title.isEmpty {
            return "删除「\(title)」"
        }
        return "删除该对话"
    }

    private var confirmationBinding: Binding<Bool> {
        Binding(
            get: { pendingDelete != nil },
            set: { if !$0 { pendingDelete = nil } }
        )
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "bubble.left.and.bubble.right")
                .font(.system(size: 56))
                .foregroundStyle(.tertiary)
            Text("还没有对话")
                .font(.headline)
            Text("点击右上角的笔图标开启新对话")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Button {
                path.append(.new)
            } label: {
                Label("新对话", systemImage: "square.and.pencil")
                    .foregroundStyle(.white)
            }
            .buttonStyle(.borderedProminent)
            .padding(.top, 4)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    private func errorState(_ text: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 44))
                .foregroundStyle(.red)
            Text("加载会话失败")
                .font(.headline)
            Text(text)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Button("重试") {
                Task { await viewModel.refresh() }
            }
            .buttonStyle(.borderedProminent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    private func makeChatViewModel(for route: ChatRoute) -> ChatViewModel {
        let id: String?
        switch route {
        case .new: id = nil
        case .existing(let sessionID): id = sessionID
        }
        return ChatViewModel(
            sessionID: id,
            chatAPI: ChatAPI(baseURL: AuthConfig.default.apiBaseURL),
            sessionAPI: SessionAPI(baseURL: AuthConfig.default.apiBaseURL),
            attachmentAPI: AttachmentAPI(baseURL: AuthConfig.default.apiBaseURL),
            tokenProvider: tokenProvider()
        )
    }

    private func tokenProvider() -> () -> String? {
        let appState = self.appState
        return {
            if case .signedIn(let session) = appState.phase {
                return session.accessToken
            }
            return nil
        }
    }
}

enum ChatRoute: Hashable {
    case new
    case existing(id: String)
}

private struct SessionRow: View {
    let session: ChatSession

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "bubble.left.and.text.bubble.right.fill")
                .font(.system(size: 20))
                .foregroundStyle(Color.accentColor)
                .frame(width: 44, height: 44)
                .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            VStack(alignment: .leading, spacing: 5) {
                Text(session.displayTitle)
                    .font(.body.weight(.medium))
                    .lineLimit(1)
                Text(ServerDate.relative(session.sortKey))
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 6)
    }
}
