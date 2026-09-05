import SwiftUI

struct LoginView: View {
    @EnvironmentObject private var appState: AppState
    @State private var showErrorDetail = false

    var body: some View {
        ZStack {
            backgroundGradient
                .ignoresSafeArea()

            VStack(spacing: 32) {
                Spacer()
                header
                Spacer()
                VStack(spacing: 12) {
                    signInButton
                    if AppEnvironment.current.showsSkipLogin {
                        skipLoginButton
                    }
                }
                if let error = appState.loginError {
                    errorBanner(error)
                }
                footer
            }
            .padding(.horizontal, 32)
            .padding(.bottom, 40)
        }
    }

    private var backgroundGradient: some View {
        LinearGradient(
            colors: [
                Color(red: 0.0, green: 0.18, blue: 0.45),
                Color(red: 0.0, green: 0.36, blue: 0.69)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    private var header: some View {
        VStack(spacing: 12) {
            Image(systemName: "graduationcap.fill")
                .resizable()
                .scaledToFit()
                .frame(width: 84, height: 84)
                .foregroundStyle(.white)
                .padding(24)
                .background(.white.opacity(0.12), in: Circle())
                .overlay(Circle().stroke(.white.opacity(0.18), lineWidth: 1))
            Text("启智")
                .font(.system(.largeTitle, design: .rounded).weight(.bold))
                .foregroundStyle(.white)
            Text("MentorAI")
                .font(.system(.subheadline, design: .rounded).weight(.medium))
                .foregroundStyle(.white.opacity(0.55))
                .tracking(2)
            Text("使用浙大通行证登录")
                .font(.subheadline)
                .foregroundStyle(.white.opacity(0.8))
        }
    }

    private var signInButton: some View {
        Button {
            Task { await appState.signIn() }
        } label: {
            HStack(spacing: 12) {
                if appState.isAuthenticating {
                    ProgressView()
                        .progressViewStyle(.circular)
                        .tint(.white)
                } else {
                    Image(systemName: "person.badge.key.fill")
                }
                Text(appState.isAuthenticating ? "正在打开登录…" : "浙大通行证登录")
                    .font(.headline)
            }
            .frame(maxWidth: .infinity, minHeight: 54)
            .foregroundStyle(.white)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(Color.white.opacity(0.18))
                    .overlay(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .stroke(.white.opacity(0.35), lineWidth: 1)
                    )
            )
        }
        .disabled(appState.isAuthenticating)
        .accessibilityIdentifier("loginButton")
    }

    /// Test-environment only: skip ZJU passport and sign in as the seeded test user
    /// (`暂不登录` → `AppState.skipLogin`, which targets the test backend).
    private var skipLoginButton: some View {
        Button {
            Task { await appState.skipLogin() }
        } label: {
            Text("暂不登录")
                .font(.subheadline.weight(.medium))
                .frame(maxWidth: .infinity, minHeight: 48)
                .foregroundStyle(.white.opacity(0.85))
                .background(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(.white.opacity(0.3), lineWidth: 1)
                )
        }
        .disabled(appState.isAuthenticating)
        .accessibilityIdentifier("skipLoginButton")
    }

    private func errorBanner(_ error: AuthError) -> some View {
        Button {
            showErrorDetail = true
        } label: {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "exclamationmark.triangle.fill")
                Text(error.errorDescription ?? "登录失败。")
                    .multilineTextAlignment(.leading)
                    .font(.footnote)
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .foregroundStyle(.white)
            .background(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(.red.opacity(0.32))
            )
        }
        .alert("登录失败", isPresented: $showErrorDetail) {
            Button("好", role: .cancel) {}
        } message: {
            Text(error.errorDescription ?? "未知错误。")
        }
    }

    private var footer: some View {
        Text("登录即表示您同意通过浙江大学统一身份认证完成登录。")
            .font(.caption)
            .multilineTextAlignment(.center)
            .foregroundStyle(.white.opacity(0.6))
    }
}

#Preview {
    LoginView().environmentObject(AppState.preview)
}
