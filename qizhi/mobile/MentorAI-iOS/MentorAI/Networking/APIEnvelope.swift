import Foundation

struct APIEnvelope<T: Decodable>: Decodable {
    let success: Bool?
    let code: Int?
    let message: String?
    let error: String?
    let data: T?

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AnyStringKey.self)
        success = try? c.decodeIfPresent(Bool.self, forKey: AnyStringKey("success"))
        code = c.firstInt(["code", "status", "errcode", "errCode"])
        message = c.firstString(["message", "msg", "errmsg", "errMsg"])
        error = c.firstString(["error"])
        data = c.firstDecodable(T.self, ["data", "result", "payload"])
    }

    var isSuccess: Bool {
        if let success { return success }
        if let code { return code == 0 || code == 200 }
        if error != nil { return false }
        return true
    }

    var errorMessage: String? {
        if let error, !error.isEmpty { return error }
        if let message, !message.isEmpty { return message }
        return nil
    }
}

struct EmptyDecodable: Decodable {
    init(from decoder: Decoder) throws {}
}
