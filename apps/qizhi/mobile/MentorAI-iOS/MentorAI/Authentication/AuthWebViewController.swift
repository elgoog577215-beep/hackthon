import UIKit
import WebKit
import os

protocol AuthWebViewControllerDelegate: AnyObject {
    @MainActor func authWebView(_ controller: AuthWebViewController, didIntercept callbackURL: URL)
    @MainActor func authWebView(_ controller: AuthWebViewController, didFailWith error: Error)
    @MainActor func authWebViewDidCancel(_ controller: AuthWebViewController)
}

final class AuthWebViewController: UIViewController {
    weak var delegate: AuthWebViewControllerDelegate?

    private let authURL: URL
    private let redirectURI: URL
    private var webView: WKWebView!
    private var progressView: UIProgressView!
    private var observation: NSKeyValueObservation?
    private let log = Logger(subsystem: "com.mentorai.app", category: "AuthWebView")

    init(authURL: URL, redirectURI: URL) {
        self.authURL = authURL
        self.redirectURI = redirectURI
        super.init(nibName: nil, bundle: nil)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) is not supported")
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        title = "ZJU Login"
        navigationItem.leftBarButtonItem = UIBarButtonItem(
            barButtonSystemItem: .cancel,
            target: self,
            action: #selector(handleCancel)
        )

        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = WKWebsiteDataStore.nonPersistent()
        if #available(iOS 14.0, *) {
            configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        }

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = self
        webView.allowsBackForwardNavigationGestures = true
        webView.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(webView)
        self.webView = webView

        let progressView = UIProgressView(progressViewStyle: .bar)
        progressView.translatesAutoresizingMaskIntoConstraints = false
        progressView.progressTintColor = view.tintColor
        view.addSubview(progressView)
        self.progressView = progressView

        NSLayoutConstraint.activate([
            progressView.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            progressView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            progressView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            progressView.heightAnchor.constraint(equalToConstant: 2),

            webView.topAnchor.constraint(equalTo: progressView.bottomAnchor),
            webView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            webView.bottomAnchor.constraint(equalTo: view.bottomAnchor)
        ])

        observation = webView.observe(\.estimatedProgress, options: [.new]) { [weak self] webView, _ in
            guard let self else { return }
            let value = Float(webView.estimatedProgress)
            self.progressView.setProgress(value, animated: true)
            self.progressView.isHidden = value >= 0.999
        }

        log.info("Loading auth URL: \(self.authURL.absoluteString, privacy: .public)")
        log.info("Watching for redirect to: \(self.redirectURI.absoluteString, privacy: .public)")
        webView.load(URLRequest(url: authURL))
    }

    deinit {
        observation?.invalidate()
    }

    @objc private func handleCancel() {
        log.info("User tapped Cancel")
        delegate?.authWebViewDidCancel(self)
    }

    private func matchesRedirect(_ url: URL) -> Bool {
        guard let candidate = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let target = URLComponents(url: redirectURI, resolvingAgainstBaseURL: false) else {
            return false
        }
        guard let candHost = candidate.host?.lowercased(),
              let tgtHost = target.host?.lowercased(),
              candHost == tgtHost else { return false }
        let candScheme = (candidate.scheme ?? "").lowercased()
        let tgtScheme = (target.scheme ?? "").lowercased()
        guard candScheme == tgtScheme else { return false }
        if !target.path.isEmpty, target.path != "/" {
            if candidate.path != target.path { return false }
        }
        let hasCode = candidate.queryItems?.contains(where: { $0.name == "code" }) ?? false
        let hasError = candidate.queryItems?.contains(where: { $0.name == "error" }) ?? false
        return hasCode || hasError
    }
}

extension AuthWebViewController: WKNavigationDelegate {
    func webView(_ webView: WKWebView,
                 decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else {
            decisionHandler(.allow)
            return
        }
        let matched = matchesRedirect(url)
        log.debug("nav → \(url.absoluteString, privacy: .public)  match=\(matched, privacy: .public)")
        if matched {
            decisionHandler(.cancel)
            delegate?.authWebView(self, didIntercept: url)
            return
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        if isCancellation(error) { return }
        log.error("didFail: \(error.localizedDescription, privacy: .public)")
        delegate?.authWebView(self, didFailWith: error)
    }

    func webView(_ webView: WKWebView,
                 didFailProvisionalNavigation navigation: WKNavigation!,
                 withError error: Error) {
        if isCancellation(error) { return }
        let nsError = error as NSError
        log.error("didFailProvisional: \(nsError.domain, privacy: .public) #\(nsError.code) — \(nsError.localizedDescription, privacy: .public)")
        delegate?.authWebView(self, didFailWith: error)
    }

    private func isCancellation(_ error: Error) -> Bool {
        let nsError = error as NSError
        return nsError.domain == NSURLErrorDomain && nsError.code == NSURLErrorCancelled
    }
}
