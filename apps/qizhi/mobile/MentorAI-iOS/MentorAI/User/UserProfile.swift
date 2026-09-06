import Foundation

struct UserProfile: Codable, Equatable {
    var id: String?
    var zjuID: String?
    var name: String?
    var department: String?
    var phone: String?
    var email: String?
    var createTime: String?

    enum CodingKeys: String, CodingKey {
        case id
        case zjuID = "zju_id"
        case name
        case department
        case phone
        case email
        case createTime = "create_time"
    }
}

extension UserProfile {
    var displayName: String {
        if let name, !name.isEmpty { return name }
        if let zjuID, !zjuID.isEmpty { return zjuID }
        if let id, !id.isEmpty { return id }
        return "—"
    }

    var formattedCreateTime: String? {
        guard let raw = createTime, !raw.isEmpty else { return nil }
        return ServerDate.absolute(raw)
    }
}
