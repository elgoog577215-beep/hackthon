import SwiftUI

struct HomeView: View {
    @EnvironmentObject private var appState: AppState
    @State private var showFeedback: Bool = false

    var body: some View {
        NavigationStack {
            List {
                if let profile = appState.currentUser {
                    profileHeader(profile)
                }
                profileSection
                actionsSection
            }
            .listStyle(.insetGrouped)
            .refreshable {
                await appState.refreshCurrentUser()
            }
            .navigationTitle("我的")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("退出登录") { appState.signOut() }
                }
            }
            .sheet(isPresented: $showFeedback) {
                FeedbackView(viewModel: makeFeedbackViewModel())
            }
        }
    }

    @ViewBuilder
    private var actionsSection: some View {
        Section {
            Button {
                showFeedback = true
            } label: {
                Label("意见反馈", systemImage: "exclamationmark.bubble")
                    .foregroundStyle(.primary)
                    .imageScale(.small)
            }
        } header: {
            Text("帮助与反馈")
        } footer: {
            Text("您的评分与建议会直接发送给启智团队，附件可选。")
        }
    }

    private func makeFeedbackViewModel() -> FeedbackViewModel {
        let baseURL = AuthConfig.default.apiBaseURL
        return FeedbackViewModel(
            feedbackAPI: FeedbackAPI(baseURL: baseURL),
            attachmentAPI: AttachmentAPI(baseURL: baseURL),
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

    @ViewBuilder
    private var profileSection: some View {
        Section {
            if let profile = appState.currentUser {
                ProfileRow(label: "用户 ID", value: profile.id)
                ProfileRow(label: "学工号", value: profile.zjuID)
                ProfileRow(label: "电话", value: profile.phone)
                ProfileRow(label: "邮箱", value: profile.email)
                ProfileRow(label: "注册时间", value: profile.formattedCreateTime)
            } else if appState.isLoadingProfile {
                HStack(spacing: 12) {
                    ProgressView()
                    Text("正在加载用户信息…")
                        .foregroundStyle(.secondary)
                }
            } else if let error = appState.profileError {
                VStack(alignment: .leading, spacing: 8) {
                    Label("无法加载用户信息", systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    Button("重试") {
                        Task { await appState.refreshCurrentUser() }
                    }
                }
            } else {
                Text("尚未加载用户信息。")
                    .foregroundStyle(.secondary)
            }
        } header: {
            Text("个人资料")
        }
    }

    private func profileHeader(_ profile: UserProfile) -> some View {
        Section {
            HStack(spacing: 14) {
                Text(profileInitial(profile))
                    .font(.title2.weight(.semibold))
                    .foregroundStyle(.white)
                    .frame(width: 56, height: 56)
                    .background(Color.accentColor.gradient, in: Circle())
                VStack(alignment: .leading, spacing: 3) {
                    Text(profile.displayName)
                        .font(.title3.weight(.semibold))
                        .lineLimit(1)
                    if let subtitle = profileSubtitle(profile) {
                        Text(subtitle)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
                Spacer(minLength: 0)
            }
            .padding(.vertical, 6)
        }
    }

    private func profileInitial(_ profile: UserProfile) -> String {
        profile.displayName.first.map { String($0).uppercased() } ?? "?"
    }

    private func profileSubtitle(_ profile: UserProfile) -> String? {
        if let department = profile.department, !department.isEmpty { return department }
        if let zjuID = profile.zjuID, !zjuID.isEmpty { return zjuID }
        if let email = profile.email, !email.isEmpty { return email }
        return nil
    }
}

private struct ProfileRow: View {
    let label: String
    let value: String?

    var body: some View {
        let display = (value?.isEmpty == false) ? value! : "—"
        LabeledContent(label) {
            Text(display)
                .foregroundStyle(display == "—" ? .secondary : .primary)
                .textSelection(.enabled)
                .multilineTextAlignment(.trailing)
        }
    }
}

#Preview {
    HomeView()
        .environmentObject(AppState.preview)
}
