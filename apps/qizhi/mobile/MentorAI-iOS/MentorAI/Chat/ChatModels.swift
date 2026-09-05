import Foundation

enum ChatRole: String, Codable {
    case user
    case assistant
    case system
}

struct ChatMessage: Codable, Equatable {
    var role: ChatRole
    var type: String
    var content: String
    var sessionID: String?

    enum CodingKeys: String, CodingKey {
        case role, type, content
        case sessionID = "session_id"
    }

    init(role: ChatRole, content: String, type: String = "text", sessionID: String? = nil) {
        self.role = role
        self.type = type
        self.content = content
        self.sessionID = sessionID
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let roleString = try c.decode(String.self, forKey: .role)
        self.role = ChatRole(rawValue: roleString) ?? .assistant
        self.type = try c.decodeIfPresent(String.self, forKey: .type) ?? "text"
        self.content = try c.decodeIfPresent(String.self, forKey: .content) ?? ""
        self.sessionID = try c.decodeIfPresent(String.self, forKey: .sessionID)
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(role.rawValue, forKey: .role)
        try c.encode(type, forKey: .type)
        try c.encode(content, forKey: .content)
        try c.encodeIfPresent(sessionID, forKey: .sessionID)
    }
}

struct ChatSession: Codable, Identifiable, Equatable {
    var id: String
    var title: String
    var createTime: String
    var updateTime: String
    var messages: [ChatMessage]

    enum CodingKeys: String, CodingKey {
        case id, title, messages
        case createTime = "create_time"
        case updateTime = "update_time"
    }

    init(id: String, title: String, createTime: String, updateTime: String, messages: [ChatMessage] = []) {
        self.id = id
        self.title = title
        self.createTime = createTime
        self.updateTime = updateTime
        self.messages = messages
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.decode(String.self, forKey: .id)
        self.title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        self.createTime = try c.decodeIfPresent(String.self, forKey: .createTime) ?? ""
        self.updateTime = try c.decodeIfPresent(String.self, forKey: .updateTime) ?? ""
        self.messages = try c.decodeIfPresent([ChatMessage].self, forKey: .messages) ?? []
    }
}

extension ChatSession {
    var displayTitle: String {
        title.isEmpty ? "新对话" : title
    }

    var sortKey: String {
        updateTime.isEmpty ? createTime : updateTime
    }
}

struct ChatSendRequest: Encodable {
    var sessionID: String?
    var query: String
    var filePaths: [String]?
    var extraParams: [String: String]?

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: AnyStringKey.self)
        try c.encode(query, forKey: AnyStringKey("query"))
        if let sessionID, !sessionID.isEmpty {
            try c.encode(sessionID, forKey: AnyStringKey("session_id"))
        }
        if let filePaths, !filePaths.isEmpty {
            try c.encode(filePaths, forKey: AnyStringKey("file_paths"))
        }
        if let extraParams, !extraParams.isEmpty {
            try c.encode(extraParams, forKey: AnyStringKey("extra_params"))
        }
    }
}
