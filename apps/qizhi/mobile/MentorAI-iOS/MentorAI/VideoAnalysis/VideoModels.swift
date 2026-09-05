import Foundation

enum VideoStatus: String, Codable, Equatable {
    case unstarted
    case waiting
    case success
    case failed

    var displayLabel: String {
        switch self {
        case .unstarted: return "未开始分析"
        case .waiting:   return "分析中"
        case .success:   return "已完成"
        case .failed:    return "分析失败"
        }
    }

    var iconName: String {
        switch self {
        case .unstarted: return "circle.dashed"
        case .waiting:   return "hourglass"
        case .success:   return "checkmark.seal.fill"
        case .failed:    return "exclamationmark.triangle.fill"
        }
    }
}

enum VideoOperation: String, Codable {
    // Raw values must stay lowercase to match the server's OperationEnum ("create"/"update"/"delete").
    case create
    case update
    case delete
}

struct VideoSummary: Codable, Identifiable, Equatable {
    var id: String
    var name: String
    var status: VideoStatus
    var cover: String?
    var analysisStartTime: String?
    var createTime: String
    /// 本地分析预估剩余秒数（仅本地分析「分析中」、含排队；云端分析为 nil）。
    var estimatedSeconds: Int?

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AnyStringKey.self)
        self.id = c.firstString(["id"]) ?? UUID().uuidString
        self.name = c.firstString(["name"]) ?? "未命名视频"
        let raw = c.firstString(["status"]) ?? "unstarted"
        self.status = VideoStatus(rawValue: raw) ?? .unstarted
        self.cover = c.firstString(["cover"])
        self.analysisStartTime = c.firstString(["analysis_start_time", "analysisStartTime"])
        self.createTime = c.firstString(["create_time", "createTime"]) ?? ""
        self.estimatedSeconds = c.firstInt(["estimated_seconds", "estimatedSeconds"])
    }

    init(id: String, name: String, status: VideoStatus, createTime: String, cover: String? = nil) {
        self.id = id
        self.name = name
        self.status = status
        self.cover = cover
        self.analysisStartTime = nil
        self.createTime = createTime
        self.estimatedSeconds = nil
    }
}

/// A per-window metric series (语速 CPM / 音量 dB / 信息密度) with backend-provided stats.
struct MetricSeries: Equatable {
    let samples: [Double]
    let avg: Double
    let max: Double
    let min: Double
    let unit: String
    let totalDuration: Double?
}

struct FillerExample: Identifiable, Equatable {
    let id = UUID()
    let time: Double
    let text: String
}

/// 语言精炼度: one filler/crutch word with its occurrence count and example utterances.
struct FillerWord: Identifiable, Equatable {
    let id = UUID()
    let term: String
    let count: Int
    let examples: [FillerExample]
}

/// 导入/总结环节分析: a graded analysis of a single phase.
struct PhaseAnalysis: Equatable {
    let score: Int
    let exists: Bool
    let evaluation: String
    let timeRange: String
    let description: String
}

/// 高频关键词: a word-cloud entry with a backend-assigned weight.
struct WordWeight: Identifiable, Equatable {
    let id = UUID()
    let word: String
    let weight: Int
}

/// 知识点分布: a node in the knowledge tree (recursive).
struct KnowledgeNode: Identifiable, Equatable {
    let id = UUID()
    let title: String
    let timeRange: String
    let children: [KnowledgeNode]
}

/// 互动事件: a single classroom interaction on the timeline.
struct InteractionEvent: Identifiable, Equatable {
    let id = UUID()
    let time: Double
    let type: String
    let text: String
}

/// 思政事件: an ideological-integration moment with a naturalness score.
struct IdeologyEvent: Identifiable, Equatable {
    let id = UUID()
    let title: String
    let content: String
    let score: Int
    let evaluation: String
    let timeRange: String
}

struct RadarAxis: Identifiable, Equatable {
    let id = UUID()
    let label: String
    let value: Double
}

struct TeachSegment: Identifiable, Equatable {
    let id = UUID()
    let type: String
    let startTime: String
    let endTime: String
    let content: String
    let keypoint: String
}

struct TeachSummarySection: Identifiable, Equatable {
    let id = UUID()
    let summary: String
    let segments: [TeachSegment]
}

struct ChartSlice: Identifiable, Equatable {
    let id = UUID()
    let label: String
    let count: Int
}

/// Video 二次分析结果 (V2 five-dimension schema). Mirrors the web `VideoAnalysisReportNewView`:
/// 整体评价 (radar_data + ai_summary), 教学表达, 教学设计, 知识呈现, 互动质量, 思政融合.
/// Every sub-object is optional; nulls and unknown extra keys are tolerated.
struct VideoAnalysisResult: Decodable, Equatable {
    // 整体评价
    var radarAxes: [RadarAxis]
    var overallScore: Int?
    var aiSummary: String?
    var aiSuggestions: [String]
    // 教学表达
    var speechRate: MetricSeries?
    var volume: MetricSeries?
    var fillerWords: [FillerWord]
    var fillerRatio: Double?
    var fillerCount: Int?
    // 教学设计
    var designSegments: [TeachSegment]
    var typeDistribution: [ChartSlice]
    var introAnalysis: PhaseAnalysis?
    var conclusionAnalysis: PhaseAnalysis?
    var infoDensity: [Double]
    // 知识呈现
    var wordCloud: [WordWeight]
    var knowledgeTree: [KnowledgeNode]
    // 互动质量
    var interactionEvents: [InteractionEvent]
    var typeStatistics: [ChartSlice]
    var whSlices: [ChartSlice]
    // 思政融合
    var ideologyEvents: [IdeologyEvent]
    // 页眉
    var audioDuration: Double?

    private static let whOrder = ["若何", "是何", "为何", "如何", "由何"]

    /// Legacy-schema parse — videos analyzed before the server's V2 ("只存新结构") migration
    /// stored the old ResourceAnalysisReportView shape (teach_summary / teach_db_result /
    /// knowledge_graph / teach_wh / teach_question / class_education_summary …). Mapped onto the
    /// same display fields so old videos still render. Kept in its own initializer so neither
    /// this nor the V2 `init(from:)` body exceeds the Swift type-checker's per-function budget.
    private init(legacyContainer c: KeyedDecodingContainer<AnyStringKey>) {
        // 整体评价: legacy carries no radar in most cases; surface the course summary as 总评.
        let tsValue = c.firstDecodable(JSONValue.self, ["teach_summary"])?.unwrappedJSON
        let summaryObj = tsValue?.arrayValue?.first?.objectValue ?? tsValue?.objectValue
        self.aiSummary = summaryObj?["summary"]?.stringValue ?? summaryObj?["text"]?.stringValue
        self.aiSuggestions = []
        var axes: [RadarAxis] = []
        var overall: Int?
        if let rc = c.firstDecodable(JSONValue.self, ["radar_chart"])?.unwrappedJSON.objectValue {
            for key in rc.keys.sorted() {
                guard let score = rc[key]?.doubleValue else { continue }
                if key == "综合得分" { overall = Int(score.rounded()) }
                else { axes.append(RadarAxis(label: key, value: score)) }
            }
        }
        if overall == nil, !axes.isEmpty {
            overall = Int((axes.map(\.value).reduce(0, +) / Double(axes.count)).rounded())
        }
        self.radarAxes = axes
        self.overallScore = overall

        // 教学表达: teach_db_result.data.result is a 音量(dB) sample series.
        let tdb = c.firstDecodable(JSONValue.self, ["teach_db_result"])?.unwrappedJSON.objectValue
        let volSamples = (tdb?["data"]?.objectValue?["result"]?.arrayValue ?? []).compactMap { $0.doubleValue }
        self.volume = volSamples.isEmpty ? nil : MetricSeries(
            samples: volSamples,
            avg: volSamples.reduce(0, +) / Double(volSamples.count),
            max: volSamples.max() ?? 0,
            min: volSamples.min() ?? 0,
            unit: "dB",
            totalDuration: nil
        )
        self.speechRate = nil
        self.fillerWords = []
        self.fillerRatio = nil
        self.fillerCount = nil

        // 教学设计: teach_summary[].file_structure → 环节 segments + 类型占比.
        var segs: [TeachSegment] = []
        for item in (summaryObj?["file_structure"]?.arrayValue ?? []) {
            guard let o = item.objectValue else { continue }
            segs.append(TeachSegment(
                type: o["type"]?.stringValue ?? "",
                startTime: o["start_time"]?.stringValue ?? "",
                endTime: o["end_time"]?.stringValue ?? "",
                content: o["content"]?.stringValue ?? "",
                keypoint: o["keypoint"]?.stringValue ?? ""
            ))
        }
        self.designSegments = segs
        var typeOrder: [String] = []
        var typeCount: [String: Int] = [:]
        for s in segs where !s.type.isEmpty {
            if typeCount[s.type] == nil { typeOrder.append(s.type) }
            typeCount[s.type, default: 0] += 1
        }
        self.typeDistribution = typeOrder.map { ChartSlice(label: $0, count: typeCount[$0] ?? 0) }
        self.introAnalysis = nil
        self.conclusionAnalysis = nil
        self.infoDensity = []

        // 知识呈现: teach_knowledge[].file_structure (title-based) → 知识树, else knowledge_graph (word-based).
        let tkStruct = (c.firstDecodable(JSONValue.self, ["teach_knowledge"])?.unwrappedJSON.arrayValue ?? [])
            .first?.objectValue?["file_structure"]?.arrayValue ?? []
        let tree: [KnowledgeNode]
        if !tkStruct.isEmpty {
            tree = Self.knowledgeNodes(tkStruct)
        } else {
            let kg = c.firstDecodable(JSONValue.self, ["knowledge_graph"])?.unwrappedJSON
                .objectValue?["result"]?.objectValue?["result"]?.arrayValue ?? []
            tree = Self.legacyKnowledgeNodes(kg)
        }
        self.knowledgeTree = tree
        self.wordCloud = Self.wordCloudFromTree(tree)

        // 互动质量: teach_question 统计/事件 + teach_wh 五何分布.
        let tq = c.firstDecodable(JSONValue.self, ["teach_question"])?.unwrappedJSON.objectValue
        var typeStats: [ChartSlice] = []
        for (key, value) in (tq?["statistics"]?.objectValue ?? [:]) {
            let n = Int(value.objectValue?["count"]?.doubleValue ?? 0)
            if n > 0 { typeStats.append(ChartSlice(label: key, count: n)) }
        }
        typeStats.sort { $0.count > $1.count }
        self.typeStatistics = typeStats
        var questionEvents: [InteractionEvent] = []
        for item in (tq?["questions"]?.arrayValue ?? []) {
            guard let o = item.objectValue else { continue }
            let text = o["text"]?.stringValue ?? ""
            guard !text.isEmpty else { continue }
            let startText = o["start_time"]?.stringValue ?? ""
            questionEvents.append(InteractionEvent(
                time: Self.timeToSeconds(startText),
                type: o["type"]?.stringValue ?? "",
                text: text
            ))
        }
        self.interactionEvents = questionEvents
        var whCount: [String: Int] = [:]
        for item in (c.firstDecodable(JSONValue.self, ["teach_wh"])?.unwrappedJSON.arrayValue ?? []) {
            guard let cat = item.objectValue?["category"]?.stringValue, !cat.isEmpty else { continue }
            whCount[cat, default: 0] += 1
        }
        var legacyWh: [ChartSlice] = []
        for key in Self.whOrder where (whCount[key] ?? 0) > 0 {
            legacyWh.append(ChartSlice(label: key, count: whCount[key] ?? 0))
        }
        for key in whCount.keys.sorted() where !Self.whOrder.contains(key) {
            legacyWh.append(ChartSlice(label: key, count: whCount[key] ?? 0))
        }
        self.whSlices = legacyWh

        // 思政融合: class_education_summary.summary[].result {title, content}.
        let ces = c.firstDecodable(JSONValue.self, ["class_education_summary"])?.unwrappedJSON.objectValue
        var ideology: [IdeologyEvent] = []
        for item in (ces?["summary"]?.arrayValue ?? []) {
            guard let o = item.objectValue, let r = o["result"]?.objectValue else { continue }
            let content = r["content"]?.stringValue ?? ""
            guard !content.isEmpty else { continue }
            let start = o["start"]?.doubleValue
            let end = o["end"]?.doubleValue
            let range = (start != nil || end != nil) ? "\(Self.clock(start ?? 0)) - \(Self.clock(end ?? 0))" : ""
            ideology.append(IdeologyEvent(
                title: r["title"]?.stringValue ?? "思政融合",
                content: content,
                score: 0,
                evaluation: "",
                timeRange: range
            ))
        }
        self.ideologyEvents = ideology

        self.audioDuration = c.firstDecodable(JSONValue.self, ["audio_duration"])?.unwrappedJSON.doubleValue
            ?? self.volume?.totalDuration
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AnyStringKey.self)

        // ---- Legacy schema fallback -------------------------------------------------
        // Videos analyzed before the server's V2 ("只存新结构") migration store the old
        // ResourceAnalysisReportView shape (teach_summary / teach_db_result / knowledge_graph
        // / teach_wh / teach_question / class_education_summary …). The V2 parser below finds
        // none of its keys, so such a video would show "暂无分析数据". Detect the legacy shape
        // and map it onto the same display fields so old videos still render their charts.
        let hasV2 = c.firstDecodable(JSONValue.self, [
            "radar_data", "teaching_expression", "teaching_design",
            "knowledge_presentation", "interaction_quality", "ideological_integration",
        ]) != nil
        let hasLegacy = c.firstDecodable(JSONValue.self, [
            "teach_summary", "teach_db_result", "knowledge_graph", "teach_wh",
            "teach_question", "class_education_summary", "teach_knowledge",
        ]) != nil
        if hasLegacy && !hasV2 {
            self = VideoAnalysisResult(legacyContainer: c)
            return
        }

        // 雷达图 / 综合得分: radar_data is [{dimension, score}]; the 综合得分 entry is the overall score.
        var axes: [RadarAxis] = []
        var overall: Int?
        for item in c.firstDecodable(JSONValue.self, ["radar_data"])?.unwrappedJSON.arrayValue ?? [] {
            guard let object = item.objectValue,
                  let dimension = object["dimension"]?.stringValue,
                  let score = object["score"]?.doubleValue else { continue }
            if dimension == "综合得分" {
                overall = Int(score.rounded())
            } else {
                axes.append(RadarAxis(label: dimension, value: score))
            }
        }
        if overall == nil,
           let v = c.firstDecodable(JSONValue.self, ["scores"])?.unwrappedJSON.objectValue?["overall"]?.doubleValue {
            overall = Int(v.rounded())
        }
        if overall == nil, !axes.isEmpty {
            overall = Int((axes.map(\.value).reduce(0, +) / Double(axes.count)).rounded())
        }
        self.radarAxes = axes
        self.overallScore = overall

        // AI 总评 / 改进建议: ai_summary = { summary, suggestions } (or a bare string).
        let ai = c.firstDecodable(JSONValue.self, ["ai_summary"])?.unwrappedJSON
        if let text = ai?.stringValue {
            self.aiSummary = text
            self.aiSuggestions = []
        } else {
            self.aiSummary = ai?.objectValue?["summary"]?.stringValue
            self.aiSuggestions = (ai?.objectValue?["suggestions"]?.arrayValue ?? [])
                .compactMap { $0.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
        }

        // 教学表达: 语速 / 音量 series + 语言精炼度（口头禅）.
        let te = c.firstDecodable(JSONValue.self, ["teaching_expression"])?.unwrappedJSON.objectValue
        self.speechRate = Self.metricSeries(te?["speech_rate_analysis"], avg: "avg_cpm", max: "max_cpm", min: "min_cpm", unit: "CPM")
        self.volume = Self.metricSeries(te?["volume_analysis"], avg: "avg_spl", max: "max_spl", min: "min_spl", unit: "dB")
        let conciseness = te?["language_conciseness"]?.objectValue
        self.fillerRatio = conciseness?["filler_word_ratio"]?.doubleValue
        self.fillerCount = conciseness?["filler_word_count"]?.doubleValue.map { Int($0) }
        self.fillerWords = (conciseness?["top_filler_words"]?.arrayValue ?? []).compactMap { item in
            guard let object = item.objectValue, let term = object["term"]?.stringValue else { return nil }
            let examples = (object["examples"]?.arrayValue ?? []).compactMap { ex -> FillerExample? in
                guard let eo = ex.objectValue, let text = eo["text"]?.stringValue, !text.isEmpty else { return nil }
                return FillerExample(time: eo["start"]?.doubleValue ?? 0, text: text)
            }
            return FillerWord(term: term, count: Int(object["count"]?.doubleValue ?? 0), examples: examples)
        }

        // 教学设计: 环节 segments、占比、导入/总结分析、信息密度.
        let td = c.firstDecodable(JSONValue.self, ["teaching_design"])?.unwrappedJSON.objectValue
        self.designSegments = (td?["segments"]?.arrayValue ?? []).compactMap { item in
            guard let object = item.objectValue else { return nil }
            return TeachSegment(
                type: object["type"]?.stringValue ?? "",
                startTime: object["start_time"]?.stringValue ?? "",
                endTime: object["end_time"]?.stringValue ?? "",
                content: object["content"]?.stringValue ?? "",
                keypoint: object["keypoint_name"]?.stringValue ?? ""
            )
        }
        self.typeDistribution = (td?["type_distribution"]?.arrayValue ?? []).compactMap { item in
            guard let object = item.objectValue, let type = object["type"]?.stringValue else { return nil }
            let duration = object["duration_seconds"]?.doubleValue ?? 0
            let count = Int(object["count"]?.doubleValue ?? 0)
            return ChartSlice(label: type, count: duration > 0 ? Int(duration.rounded()) : count)
        }
        self.introAnalysis = Self.phaseAnalysis(td?["introduction_analysis"])
        self.conclusionAnalysis = Self.phaseAnalysis(td?["conclusion_analysis"])
        self.infoDensity = (td?["information_density"]?.objectValue?["result"]?.arrayValue ?? []).compactMap { $0.doubleValue }

        // 知识呈现: 词云（含权重）+ 知识树.
        let kp = c.firstDecodable(JSONValue.self, ["knowledge_presentation"])?.unwrappedJSON.objectValue
        self.wordCloud = (kp?["word_cloud"]?.arrayValue ?? []).compactMap { item in
            guard let object = item.objectValue, let word = object["word"]?.stringValue else { return nil }
            return WordWeight(word: word, weight: Int(object["weight"]?.doubleValue ?? 0))
        }
        self.knowledgeTree = Self.knowledgeNodes(kp?["knowledge_tree"]?.arrayValue ?? [])

        // 互动质量: 事件时间轴、类型统计、五何分布.
        let iq = c.firstDecodable(JSONValue.self, ["interaction_quality"])?.unwrappedJSON.objectValue
        self.interactionEvents = (iq?["interaction_events"]?.arrayValue ?? []).compactMap { item in
            guard let object = item.objectValue else { return nil }
            let text = object["text"]?.stringValue ?? object["segment"]?.stringValue ?? ""
            guard !text.isEmpty else { return nil }
            return InteractionEvent(
                time: Self.timeToSeconds(object["start_time"]?.stringValue ?? ""),
                type: object["type"]?.stringValue ?? "",
                text: text
            )
        }
        self.typeStatistics = (iq?["type_statistics"]?.objectValue ?? [:])
            .compactMap { entry -> ChartSlice? in
                let n = Int(entry.value.doubleValue ?? 0)
                return n > 0 ? ChartSlice(label: entry.key, count: n) : nil
            }
            .sorted { $0.count > $1.count }
        var whSlices: [ChartSlice] = []
        let whObject = iq?["wh_distribution"]?.objectValue ?? [:]
        for key in Self.whOrder {
            if let count = whObject[key]?.objectValue?["count"]?.doubleValue, Int(count) > 0 {
                whSlices.append(ChartSlice(label: key, count: Int(count)))
            }
        }
        for (key, value) in whObject where !Self.whOrder.contains(key) {
            if let count = value.objectValue?["count"]?.doubleValue, Int(count) > 0 {
                whSlices.append(ChartSlice(label: key, count: Int(count)))
            }
        }
        self.whSlices = whSlices

        // 思政融合: 思政事件.
        let ii = c.firstDecodable(JSONValue.self, ["ideological_integration"])?.unwrappedJSON.objectValue
        self.ideologyEvents = (ii?["ideological_events"]?.arrayValue ?? []).compactMap { item in
            guard let object = item.objectValue else { return nil }
            let start = object["start"]?.doubleValue
            let end = object["end"]?.doubleValue
            let range = (start != nil || end != nil) ? "\(Self.clock(start ?? 0)) - \(Self.clock(end ?? 0))" : ""
            return IdeologyEvent(
                title: object["title"]?.stringValue ?? "思政事件",
                content: object["content"]?.stringValue ?? "",
                score: Int(object["integration_score"]?.doubleValue ?? 0),
                evaluation: object["integration_evaluation"]?.stringValue ?? "",
                timeRange: range
            )
        }

        self.audioDuration = self.volume?.totalDuration ?? self.speechRate?.totalDuration
    }

    /// True when any user-visible section has data.
    var hasContent: Bool {
        !radarAxes.isEmpty || overallScore != nil || aiSummary?.isEmpty == false || !aiSuggestions.isEmpty
            || volume != nil || speechRate != nil || !fillerWords.isEmpty
            || !designSegments.isEmpty || !typeDistribution.isEmpty
            || introAnalysis != nil || conclusionAnalysis != nil || !infoDensity.isEmpty
            || !wordCloud.isEmpty || !knowledgeTree.isEmpty
            || !interactionEvents.isEmpty || !typeStatistics.isEmpty || !whSlices.isEmpty
            || !ideologyEvents.isEmpty
    }

    // MARK: - Decoding helpers

    private static func metricSeries(_ value: JSONValue?, avg: String, max: String, min: String, unit: String) -> MetricSeries? {
        guard let object = value?.objectValue else { return nil }
        let samples = (object["result"]?.arrayValue ?? []).compactMap { $0.doubleValue }
        guard !samples.isEmpty else { return nil }
        return MetricSeries(
            samples: samples,
            avg: object[avg]?.doubleValue ?? (samples.reduce(0, +) / Double(samples.count)),
            max: object[max]?.doubleValue ?? (samples.max() ?? 0),
            min: object[min]?.doubleValue ?? (samples.min() ?? 0),
            unit: unit,
            totalDuration: object["total_duration"]?.doubleValue
        )
    }

    private static func phaseAnalysis(_ value: JSONValue?) -> PhaseAnalysis? {
        guard let object = value?.objectValue, !object.isEmpty else { return nil }
        return PhaseAnalysis(
            score: Int(object["score"]?.doubleValue ?? 0),
            exists: object["exists"]?.boolValue ?? true,
            evaluation: object["evaluation"]?.stringValue ?? "",
            timeRange: object["time_range"]?.stringValue ?? "",
            description: object["description"]?.stringValue ?? ""
        )
    }

    private static func knowledgeNodes(_ values: [JSONValue]) -> [KnowledgeNode] {
        values.compactMap { value in
            guard let object = value.objectValue, let title = object["title"]?.stringValue else { return nil }
            let start = object["start_time"]?.stringValue ?? ""
            let end = object["end_time"]?.stringValue ?? ""
            let range = (!start.isEmpty || !end.isEmpty) ? "\(start) - \(end)" : ""
            return KnowledgeNode(title: title, timeRange: range, children: knowledgeNodes(object["children"]?.arrayValue ?? []))
        }
    }

    /// Legacy `knowledge_graph` nodes use `word` + `time_range:{start,end}` instead of the V2
    /// `title` + `start_time`/`end_time`; map them onto the shared `KnowledgeNode` shape.
    private static func legacyKnowledgeNodes(_ values: [JSONValue]) -> [KnowledgeNode] {
        values.compactMap { value in
            guard let object = value.objectValue,
                  let word = object["word"]?.stringValue ?? object["title"]?.stringValue else { return nil }
            let tr = object["time_range"]?.objectValue
            let start = tr?["start"]?.stringValue ?? object["start_time"]?.stringValue ?? ""
            let end = tr?["end"]?.stringValue ?? object["end_time"]?.stringValue ?? ""
            let range = (!start.isEmpty || !end.isEmpty) ? "\(start) - \(end)" : ""
            return KnowledgeNode(title: word, timeRange: range, children: legacyKnowledgeNodes(object["children"]?.arrayValue ?? []))
        }
    }

    /// Derive a word cloud from a knowledge tree (legacy videos have no explicit cloud):
    /// broader topics (more descendants) weigh more. Capped so the chart stays readable.
    private static func wordCloudFromTree(_ nodes: [KnowledgeNode]) -> [WordWeight] {
        func descendants(_ n: KnowledgeNode) -> Int { n.children.reduce(n.children.count) { $0 + descendants($1) } }
        var out: [WordWeight] = []
        func walk(_ ns: [KnowledgeNode]) {
            for n in ns {
                if !n.title.isEmpty { out.append(WordWeight(word: n.title, weight: descendants(n) + 1)) }
                walk(n.children)
            }
        }
        walk(nodes)
        return Array(out.sorted { $0.weight > $1.weight }.prefix(40))
    }

    private static func timeToSeconds(_ text: String) -> Double {
        let parts = text.split(separator: ":").compactMap { Double($0) }
        guard !parts.isEmpty else { return 0 }
        return parts.reduce(0) { $0 * 60 + $1 }
    }

    private static func clock(_ seconds: Double) -> String {
        let total = Int(seconds)
        return String(format: "%d:%02d", total / 60, total % 60)
    }
}

/// Loosely-typed JSON value used to defensively parse backend fields that may arrive
/// as parsed objects, loosely-typed values, or JSON-encoded strings.
enum JSONValue: Decodable, Equatable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else {
            self = .null
        }
    }

    var stringValue: String? { if case .string(let v) = self { return v } else { return nil } }
    var doubleValue: Double? {
        switch self {
        case .number(let v): return v
        case .string(let v): return Double(v)
        default: return nil
        }
    }
    var boolValue: Bool? { if case .bool(let v) = self { return v } else { return nil } }
    var arrayValue: [JSONValue]? { if case .array(let v) = self { return v } else { return nil } }
    var objectValue: [String: JSONValue]? { if case .object(let v) = self { return v } else { return nil } }

    /// If this is a JSON-encoded string, parse it into structured JSON; otherwise return self.
    var unwrappedJSON: JSONValue {
        guard case .string(let text) = self,
              let data = text.data(using: .utf8),
              let parsed = try? JSONDecoder().decode(JSONValue.self, from: data) else {
            return self
        }
        return parsed
    }
}

struct VideoDetail: Decodable, Equatable {
    var id: String
    var name: String
    var path: String
    var status: VideoStatus
    var analysisStartTime: String?
    var analysisResult: VideoAnalysisResult?
    var createTime: String

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AnyStringKey.self)
        self.id = c.firstString(["id"]) ?? ""
        self.name = c.firstString(["name"]) ?? "未命名视频"
        self.path = c.firstString(["path"]) ?? ""
        let raw = c.firstString(["status"]) ?? "unstarted"
        self.status = VideoStatus(rawValue: raw) ?? .unstarted
        self.analysisStartTime = c.firstString(["analysis_start_time", "analysisStartTime"])
        self.analysisResult = c.firstDecodable(VideoAnalysisResult.self, ["analysis_result", "analysisResult"])
        self.createTime = c.firstString(["create_time", "createTime"]) ?? ""
    }
}

struct VideoOperationRequest: Encodable {
    var operation: VideoOperation
    var id: String?
    var name: String?
    var path: String?
    var cover: String?

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: AnyStringKey.self)
        try c.encode(operation.rawValue, forKey: AnyStringKey("operation"))
        if let id { try c.encode(id, forKey: AnyStringKey("id")) }
        if let name { try c.encode(name, forKey: AnyStringKey("name")) }
        if let path { try c.encode(path, forKey: AnyStringKey("path")) }
        if let cover { try c.encode(cover, forKey: AnyStringKey("cover")) }
    }
}

/// One flattened recording row (course × session) shown in the import picker.
struct ZhiyunCourse: Identifiable, Equatable {
    var id: String { "\(courseID)#\(subID)" }
    var courseID: String
    var subID: String
    var courseName: String
    var subTitle: String
    var teacherName: String
    var classBegin: String
}

/// `/video/zhiyun/list` now returns courses grouped by course, each carrying its session
/// items. We decode the groups and flatten them into `ZhiyunCourse` rows for display.
struct ZhiyunCourseItem: Decodable, Equatable {
    var subID: String
    var subTitle: String
    var teacherName: String
    var classBegin: String

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AnyStringKey.self)
        self.subID = c.firstString(["sub_id", "subId"]) ?? ""
        self.subTitle = c.firstString(["sub_title", "subTitle", "subtitle"]) ?? ""
        self.teacherName = c.firstString(["teacher_name", "teacherName"]) ?? ""
        self.classBegin = c.firstString(["class_begin", "classBegin"]) ?? ""
    }
}

struct ZhiyunCourseGroup: Decodable, Equatable {
    var courseID: String
    var courseName: String
    var items: [ZhiyunCourseItem]

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AnyStringKey.self)
        self.courseID = c.firstString(["course_id", "courseId"]) ?? ""
        self.courseName = c.firstString(["course_name", "courseName"]) ?? "未命名课程"
        self.items = c.firstDecodable([ZhiyunCourseItem].self, ["items"]) ?? []
    }
}
