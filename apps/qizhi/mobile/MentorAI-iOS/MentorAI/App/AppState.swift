import Foundation
import SwiftUI
import os

@MainActor
final class AppState: ObservableObject {
    enum Phase: Equatable {
        case launching
        case signedOut
        case signedIn(AuthSession)
    }

    @Published private(set) var phase: Phase = .launching
    @Published var loginError: AuthError?
    @Published private(set) var isAuthenticating: Bool = false

    @Published private(set) var currentUser: UserProfile?
    @Published private(set) var profileError: String?
    @Published private(set) var isLoadingProfile: Bool = false

    private let auth: AuthService
    private let tokens: TokenStore
    private let userAPI: UserAPI
    private let log = Logger(subsystem: "com.mentorai.app", category: "AppState")
    private static let isTestModeKey = "com.mentorai.app.isTestMode"

    /// Whether the current session was created via "暂不登录" (skip login / test mode).
    var isTestMode: Bool {
        UserDefaults.standard.bool(forKey: Self.isTestModeKey)
    }

    init(auth: AuthService = .live,
         tokens: TokenStore = .keychain,
         userAPI: UserAPI = UserAPI(baseURL: AuthConfig.default.apiBaseURL)) {
        self.auth = auth
        self.tokens = tokens
        self.userAPI = userAPI
    }

    func bootstrap() async {
        guard let session = tokens.load() else {
            phase = .signedOut
            return
        }
        if session.isExpired {
            log.info("Saved session expired; signing out")
            tokens.clear()
            UserDefaults.standard.removeObject(forKey: Self.isTestModeKey)
            phase = .signedOut
            return
        }
        // Restore the correct server environment before using the token
        if UserDefaults.standard.bool(forKey: Self.isTestModeKey) {
            log.info("Restoring test environment for saved session")
            AuthConfig.switchToTest()
        } else {
            AuthConfig.switchToProduction()
        }
        log.info("Resuming saved session")
        phase = .signedIn(session)
        await fetchCurrentUser(token: session.accessToken)
    }

    func signIn() async {
        guard !isAuthenticating else { return }
        isAuthenticating = true
        loginError = nil
        defer { isAuthenticating = false }
        AuthConfig.switchToProduction()
        do {
            let session = try await auth.signIn()
            tokens.save(session)
            UserDefaults.standard.set(false, forKey: Self.isTestModeKey)
            withAnimation(.easeInOut(duration: 0.25)) {
                phase = .signedIn(session)
            }
            await fetchCurrentUser(token: session.accessToken)
        } catch let error as AuthError {
            if case .userCancelled = error { return }
            loginError = error
        } catch {
            loginError = .unknown(error)
        }
    }

    func skipLogin() async {
        guard !isAuthenticating else { return }
        isAuthenticating = true
        loginError = nil
        defer { isAuthenticating = false }
        AuthConfig.switchToTest()
        do {
            let (name, zjuID) = Self.testCredentials()
            log.info("Skip login with name=\(name) zjuID=\(zjuID)")
            let api = AuthAPI(baseURL: AuthConfig.default.apiBaseURL)
            let response = try await api.testLogin(name: name, zjuID: zjuID)
            let session = response.session
            tokens.save(session)
            UserDefaults.standard.set(true, forKey: Self.isTestModeKey)
            withAnimation(.easeInOut(duration: 0.25)) {
                phase = .signedIn(session)
            }
            await fetchCurrentUser(token: session.accessToken)
        } catch let error as AuthError {
            AuthConfig.switchToProduction()
            loginError = error
        } catch {
            AuthConfig.switchToProduction()
            loginError = .unknown(error)
        }
    }

    func signOut() {
        tokens.clear()
        currentUser = nil
        profileError = nil
        isLoadingProfile = false
        UserDefaults.standard.removeObject(forKey: Self.isTestModeKey)
        AuthConfig.switchToProduction()
        withAnimation(.easeInOut(duration: 0.25)) {
            phase = .signedOut
        }
    }

    func refreshCurrentUser() async {
        guard case .signedIn(let session) = phase else { return }
        await fetchCurrentUser(token: session.accessToken)
    }

    private func fetchCurrentUser(token: String) async {
        profileError = nil
        isLoadingProfile = true
        defer { isLoadingProfile = false }
        do {
            let api = UserAPI(baseURL: AuthConfig.default.apiBaseURL)
            currentUser = try await api.currentUser(token: token)
            log.info("Loaded profile for \(self.currentUser?.zjuID ?? self.currentUser?.id ?? "unknown", privacy: .public)")
        } catch let error as AuthError {
            if case .server(let status, _) = error, status == 401 {
                log.warning("Server rejected token (401); signing out")
                signOut()
                return
            }
            profileError = error.errorDescription
            log.error("Profile fetch failed: \(error.errorDescription ?? "?", privacy: .public)")
        } catch {
            profileError = error.localizedDescription
            log.error("Profile fetch failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    /// Fixed "模拟登录" identity, matching the web client's "点我模拟登录" button
    /// (`POST /auth/test-login?name=测试用户&zju_id=0010759`, see `Navbar.vue` handleDevLogin).
    ///
    /// `0010759` is the seeded test account the server already has on file with a
    /// teacher/admin role, so it passes the `require_roles(TEACHER, ADMIN)` guard on the
    /// resource-analysis + operation endpoints. Generating a *random* zju_id instead (the
    /// previous behavior) made the server create a brand-new STUDENT user, which every
    /// teacher-gated call then rejected with 401「无操作权限」.
    private static func testCredentials() -> (name: String, zjuID: String) {
        ("测试用户", "0010759")
    }
}

extension AppState {
    static var preview: AppState {
        let state = AppState(auth: .live, tokens: .ephemeral)
        state.phase = .signedOut
        return state
    }
}
