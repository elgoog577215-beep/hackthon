import Foundation

enum AuthError: LocalizedError, Equatable {
    case invalidAuthURL
    case missingAuthorizationCode
    case userCancelled
    case server(status: Int, message: String?)
    case decoding(String)
    case transport(String)
    case unknown(Error)

    var errorDescription: String? {
        switch self {
        case .invalidAuthURL:
            return "登录地址格式有误。"
        case .missingAuthorizationCode:
            return "回调中缺少授权码。"
        case .userCancelled:
            return "已取消登录。"
        case .server(let status, let message):
            return message.map { "服务器错误（\(status)）：\($0)" } ?? "服务器错误（\(status)）。"
        case .decoding(let detail):
            return "解析响应失败：\(detail)"
        case .transport(let detail):
            return "网络错误：\(detail)"
        case .unknown(let error):
            return error.localizedDescription
        }
    }

    static func == (lhs: AuthError, rhs: AuthError) -> Bool {
        switch (lhs, rhs) {
        case (.invalidAuthURL, .invalidAuthURL),
             (.missingAuthorizationCode, .missingAuthorizationCode),
             (.userCancelled, .userCancelled):
            return true
        case let (.server(a, ma), .server(b, mb)):
            return a == b && ma == mb
        case let (.decoding(a), .decoding(b)):
            return a == b
        case let (.transport(a), .transport(b)):
            return a == b
        case let (.unknown(a), .unknown(b)):
            return (a as NSError) == (b as NSError)
        default:
            return false
        }
    }
}
