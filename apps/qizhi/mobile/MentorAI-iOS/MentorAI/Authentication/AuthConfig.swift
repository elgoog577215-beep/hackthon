import Foundation

/// Which backend environment this build targets. The test (internal/QA) environment defaults
/// to the test server and shows the "暂不登录" shortcut; production uses the ZJU server and
/// hides it. Driven by build configuration — flip the values below to force an environment.
enum AppEnvironment {
    case test
    case production

    #if DEBUG
    static let current: AppEnvironment = .test
    #else
    static let current: AppEnvironment = .production
    #endif

    var config: AuthConfig {
        switch self {
        case .test:       return .test
        case .production: return .production
        }
    }

    /// Whether to show the "暂不登录" (skip-login / 模拟登录) button on the login screen.
    var showsSkipLogin: Bool { self == .test }
}

struct AuthConfig {
    var apiBaseURL: URL

    static let production = AuthConfig(
        apiBaseURL: URL(string: "http://jsfzai.zju.edu.cn/api")!
    )

    static let test = AuthConfig(
        apiBaseURL: URL(string: "http://127.0.0.1:8000")!
    )

    /// Starts on the build's target environment; `switchToTest`/`switchToProduction` change it
    /// at runtime as the user picks a login method (see `AppState.skipLogin` / `signIn`).
    private static var _active: AuthConfig = AppEnvironment.current.config

    static var `default`: AuthConfig {
        get { _active }
        set { _active = newValue }
    }

    static func switchToTest() {
        _active = .test
    }

    static func switchToProduction() {
        _active = .production
    }
}
