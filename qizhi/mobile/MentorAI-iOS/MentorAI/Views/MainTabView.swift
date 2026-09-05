import SwiftUI

struct MainTabView: View {
    @EnvironmentObject private var appState: AppState
    @StateObject private var sessionListVM: SessionListViewModel
    @StateObject private var resourceListVM: ResourceListViewModel
    @StateObject private var videoListVM: VideoListViewModel
    let session: AuthSession

    init(session: AuthSession) {
        self.session = session
        let baseURL = AuthConfig.default.apiBaseURL
        let token = session.accessToken
        let userID = session.user?.id
        _sessionListVM = StateObject(wrappedValue: SessionListViewModel(
            api: SessionAPI(baseURL: baseURL),
            tokenProvider: { token }
        ))
        _resourceListVM = StateObject(wrappedValue: ResourceListViewModel(
            api: ResourceAPI(baseURL: baseURL),
            tokenProvider: { token },
            userIDProvider: { userID }
        ))
        _videoListVM = StateObject(wrappedValue: VideoListViewModel(
            api: VideoAPI(baseURL: baseURL),
            tokenProvider: { token }
        ))
    }

    var body: some View {
        TabView {
            chatTab
                .tabItem {
                    Label("对话", systemImage: "bubble.left.and.text.bubble.right.fill")
                }
//            resourceTab
//                .tabItem {
//                    Label("备课", systemImage: "doc.text.fill")
//                }
            videoTab
                .tabItem {
                    Label("资源分析", systemImage: "video.badge.waveform")
                }
            profileTab
                .tabItem {
                    Label("我的", systemImage: "person.crop.circle.fill")
                }
        }
    }

    private var chatTab: some View {
        SessionListView(viewModel: sessionListVM)
    }

    private var resourceTab: some View {
        ResourceListView(viewModel: resourceListVM)
    }

    private var videoTab: some View {
        VideoAnalysisListView(viewModel: videoListVM)
    }

    private var profileTab: some View {
        HomeView()
    }
}
