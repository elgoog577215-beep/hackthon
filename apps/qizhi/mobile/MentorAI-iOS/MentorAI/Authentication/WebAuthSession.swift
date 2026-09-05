import Foundation
import UIKit

@MainActor
final class WebAuthSession: NSObject {
    private var continuation: CheckedContinuation<URL, Error>?
    private weak var presentedNav: UINavigationController?

    func start(authURL: URL, redirectURI: URL) async throws -> URL {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<URL, Error>) in
            self.continuation = continuation
            guard let presenter = Self.topViewController() else {
                self.complete(.failure(AuthError.transport("没有可用的窗口来展示登录页面。")))
                return
            }
            let controller = AuthWebViewController(authURL: authURL, redirectURI: redirectURI)
            controller.delegate = self
            let nav = UINavigationController(rootViewController: controller)
            nav.modalPresentationStyle = .fullScreen
            nav.presentationController?.delegate = self
            self.presentedNav = nav
            presenter.present(nav, animated: true)
        }
    }

    private func complete(_ result: Result<URL, Error>) {
        guard let continuation else { return }
        self.continuation = nil
        if let nav = presentedNav {
            self.presentedNav = nil
            nav.dismiss(animated: true) {
                continuation.resume(with: result)
            }
        } else {
            continuation.resume(with: result)
        }
    }

    private static func topViewController() -> UIViewController? {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        let window = scenes.flatMap(\.windows).first(where: \.isKeyWindow) ?? scenes.first?.windows.first
        guard var top = window?.rootViewController else { return nil }
        while let presented = top.presentedViewController {
            top = presented
        }
        return top
    }
}

extension WebAuthSession: AuthWebViewControllerDelegate {
    func authWebView(_ controller: AuthWebViewController, didIntercept callbackURL: URL) {
        complete(.success(callbackURL))
    }

    func authWebView(_ controller: AuthWebViewController, didFailWith error: Error) {
        complete(.failure(AuthError.transport(error.localizedDescription)))
    }

    func authWebViewDidCancel(_ controller: AuthWebViewController) {
        complete(.failure(AuthError.userCancelled))
    }
}

extension WebAuthSession: UIAdaptivePresentationControllerDelegate {
    nonisolated func presentationControllerDidDismiss(_ presentationController: UIPresentationController) {
        Task { @MainActor in
            self.complete(.failure(AuthError.userCancelled))
        }
    }
}
