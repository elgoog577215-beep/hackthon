import Foundation

enum ResourceType: String, Codable, CaseIterable, Identifiable {
    case outline = "outline"
    case teachingPlan = "teaching_plan"
    case ppt = "ppt"
    case questionBank = "question_bank"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .outline: return "教学大纲"
        case .teachingPlan: return "教案"
        case .ppt: return "PPT"
        case .questionBank: return "题库"
        }
    }

    var iconName: String {
        switch self {
        case .outline: return "doc.text"
        case .teachingPlan: return "book.closed"
        case .ppt: return "rectangle.on.rectangle"
        case .questionBank: return "list.bullet.rectangle"
        }
    }
}

enum ResourceOperation: String, Codable {
    case create
    case update
    case delete
    case copy
}

struct RelatedCourse: Codable, Equatable {
    var id: String?
    var name: String?

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AnyStringKey.self)
        self.id = c.firstString(["id"])
        self.name = c.firstString(["name", "course_name"])
    }
}

struct RelatedUnit: Codable, Equatable {
    var id: String?
    var name: String?

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AnyStringKey.self)
        self.id = c.firstString(["id"])
        self.name = c.firstString(["name", "unit_name"])
    }
}

struct ResourceSummary: Codable, Identifiable, Equatable {
    var id: String
    var name: String
    var resourceType: ResourceType
    var wordCount: Int
    var relatedCourse: RelatedCourse?
    var relatedUnit: RelatedUnit?
    var createTime: String
    var updateTime: String

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AnyStringKey.self)
        self.id = c.firstString(["id"]) ?? UUID().uuidString
        self.name = c.firstString(["name"]) ?? "未命名资源"
        let rawType = c.firstString(["resource_type", "resourceType"]) ?? "outline"
        self.resourceType = ResourceType(rawValue: rawType) ?? .outline
        self.wordCount = c.firstInt(["word_count", "wordCount"]) ?? 0
        self.relatedCourse = c.firstDecodable(RelatedCourse.self, ["related_course", "relatedCourse"])
        self.relatedUnit = c.firstDecodable(RelatedUnit.self, ["related_unit", "relatedUnit"])
        self.createTime = c.firstString(["create_time", "createTime"]) ?? ""
        self.updateTime = c.firstString(["update_time", "updateTime"]) ?? self.createTime
    }
}

struct ResourceDetail: Codable, Equatable {
    var id: String
    var name: String
    var resourceType: ResourceType
    var content: String
    var wordCount: Int
    var relatedCourse: RelatedCourse?
    var relatedUnit: RelatedUnit?
    var createTime: String
    var updateTime: String

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AnyStringKey.self)
        self.id = c.firstString(["id"]) ?? UUID().uuidString
        self.name = c.firstString(["name"]) ?? "未命名资源"
        let rawType = c.firstString(["resource_type", "resourceType"]) ?? "outline"
        self.resourceType = ResourceType(rawValue: rawType) ?? .outline
        self.content = c.firstString(["content"]) ?? ""
        self.wordCount = c.firstInt(["word_count", "wordCount"]) ?? 0
        self.relatedCourse = c.firstDecodable(RelatedCourse.self, ["related_course", "relatedCourse"])
        self.relatedUnit = c.firstDecodable(RelatedUnit.self, ["related_unit", "relatedUnit"])
        self.createTime = c.firstString(["create_time", "createTime"]) ?? ""
        self.updateTime = c.firstString(["update_time", "updateTime"]) ?? self.createTime
    }
}

struct OutlineForm: Encodable, Equatable {
    var courseName: String = ""
    var courseNature: String = "专业必修课"
    var courseCategory: String = ""
    var credits: Int = 2
    var hours: Int = 32
    var targetMajor: String = ""
    var targetGrade: String = "大学二年级"
    var teachingMethod: String = "线上线下混合"
    var offlineHoursRatio: Int = 70
    var offlineScoreRatio: Int = 70
    var prerequisites: String = ""
    var courseIntroduction: String = ""
    var teachingObjectives: String = ""
    var ideologicalPolitical: String?

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: AnyStringKey.self)
        try c.encode(courseName, forKey: AnyStringKey("course_name"))
        try c.encode(courseNature, forKey: AnyStringKey("course_nature"))
        try c.encode(courseCategory, forKey: AnyStringKey("course_category"))
        try c.encode(credits, forKey: AnyStringKey("credits"))
        try c.encode(hours, forKey: AnyStringKey("hours"))
        try c.encode(targetMajor, forKey: AnyStringKey("target_major"))
        try c.encode(targetGrade, forKey: AnyStringKey("target_grade"))
        try c.encode(teachingMethod, forKey: AnyStringKey("teaching_method"))
        try c.encode(offlineHoursRatio, forKey: AnyStringKey("offline_hours_ratio"))
        try c.encode(offlineScoreRatio, forKey: AnyStringKey("offline_score_ratio"))
        try c.encode(prerequisites, forKey: AnyStringKey("prerequisites"))
        try c.encode(courseIntroduction, forKey: AnyStringKey("course_introduction"))
        try c.encode(teachingObjectives, forKey: AnyStringKey("teaching_objectives"))
        if let ip = ideologicalPolitical, !ip.isEmpty {
            try c.encode(ip, forKey: AnyStringKey("ideological_political"))
        }
    }

    var isValid: Bool {
        !courseName.trimmingCharacters(in: .whitespaces).isEmpty
            && !courseCategory.trimmingCharacters(in: .whitespaces).isEmpty
            && !targetMajor.trimmingCharacters(in: .whitespaces).isEmpty
            && !courseIntroduction.trimmingCharacters(in: .whitespaces).isEmpty
            && !teachingObjectives.trimmingCharacters(in: .whitespaces).isEmpty
    }
}

struct ResourceGenerateRequest: Encodable {
    var operation: ResourceOperation = .create
    var resourceType: ResourceType
    var prompt: String?
    var basicResourceID: String?
    var previousContent: String?
    var outlineForm: OutlineForm?

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: AnyStringKey.self)
        try c.encode(operation.rawValue, forKey: AnyStringKey("operation"))
        try c.encode(resourceType.rawValue, forKey: AnyStringKey("resource_type"))
        if let prompt, !prompt.isEmpty {
            try c.encode(prompt, forKey: AnyStringKey("prompt"))
        }
        if let basicResourceID, !basicResourceID.isEmpty {
            try c.encode(basicResourceID, forKey: AnyStringKey("basic_resource_id"))
        }
        if let previousContent, !previousContent.isEmpty {
            try c.encode(previousContent, forKey: AnyStringKey("previous_content"))
        }
        if let outlineForm {
            try c.encode(outlineForm, forKey: AnyStringKey("outline_form"))
        }
    }
}

struct ResourceOperationRequest: Encodable {
    var operation: ResourceOperation
    var id: String?
    var name: String?
    var resourceType: ResourceType?
    var content: String?
    var relatedCourseID: String?
    var relatedUnitID: String?

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: AnyStringKey.self)
        try c.encode(operation.rawValue, forKey: AnyStringKey("operation"))
        if let id { try c.encode(id, forKey: AnyStringKey("id")) }
        if let name { try c.encode(name, forKey: AnyStringKey("name")) }
        if let resourceType { try c.encode(resourceType.rawValue, forKey: AnyStringKey("resource_type")) }
        if let content { try c.encode(content, forKey: AnyStringKey("content")) }
        if let relatedCourseID { try c.encode(relatedCourseID, forKey: AnyStringKey("related_course_id")) }
        if let relatedUnitID { try c.encode(relatedUnitID, forKey: AnyStringKey("related_unit_id")) }
    }
}
