import SwiftUI

struct RootView: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        switch appState.phase {
        case .launching:
            SplashView()
        case .signedOut:
            LoginView()
                .transition(.opacity)
        case .signedIn(let session):
            MainTabView(session: session)
                .transition(.opacity)
        }
    }
}

private struct SplashView: View {
    var body: some View {
        VStack(spacing: 16) {
            ProgressView()
            Text("正在启动启智…")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(.systemBackground))
    }
}

#Preview {
    RootView().environmentObject(AppState.preview)
}
