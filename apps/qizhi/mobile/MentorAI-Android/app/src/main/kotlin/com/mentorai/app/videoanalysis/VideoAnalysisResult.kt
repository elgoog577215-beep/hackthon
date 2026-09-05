package com.mentorai.app.videoanalysis

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlin.math.roundToInt

/**
 * Decoded five-dimension analysis payload — mirrors the iOS `VideoAnalysisResult`. The live
 * `GET /video` returns `radar_data`, `ai_summary`, `teaching_expression`, `teaching_design`,
 * `knowledge_presentation`, `interaction_quality`, `ideological_integration` (V2). Videos analyzed
 * before the server's V2 ("只存新结构") migration store the OLD shape (`teach_summary` /
 * `teach_db_result` / `knowledge_graph` / `teach_wh` / `teach_question` / `class_education_summary`
 * / `teach_knowledge`), which [parseLegacy] maps onto the same display fields so old videos still
 * render. Parsed defensively from a `JsonElement`; every sub-object is optional and nulls are
 * tolerated. Fields that arrive as a JSON-encoded STRING are re-parsed at every top-level lookup.
 */
data class VideoAnalysisResult(
    // 整体评价
    val radarAxes: List<RadarAxis> = emptyList(),
    val overallScore: Int? = null,
    val aiSummary: String? = null,
    val aiSuggestions: List<String> = emptyList(),
    // 教学表达
    val speechRate: MetricSeries? = null,
    val volume: MetricSeries? = null,
    val fillerWords: List<FillerWord> = emptyList(),
    val fillerRatio: Double? = null,
    val fillerCount: Int? = null,
    // 教学设计
    val designSegments: List<TeachSegment> = emptyList(),
    val typeDistribution: List<ChartSlice> = emptyList(),
    val introAnalysis: PhaseAnalysis? = null,
    val conclusionAnalysis: PhaseAnalysis? = null,
    val infoDensity: List<Double> = emptyList(),
    // 知识呈现
    val wordCloud: List<WordWeight> = emptyList(),
    val knowledgeTree: List<KnowledgeNode> = emptyList(),
    // 互动质量
    val interactionEvents: List<InteractionEvent> = emptyList(),
    val typeStatistics: List<ChartSlice> = emptyList(),
    val whSlices: List<ChartSlice> = emptyList(),
    // 思政融合
    val ideologyEvents: List<IdeologyEvent> = emptyList(),
    // 页眉
    val audioDuration: Double? = null,
) {
    /** True when any user-visible section has data. */
    val hasContent: Boolean
        get() = radarAxes.isNotEmpty() || overallScore != null || !aiSummary.isNullOrEmpty() || aiSuggestions.isNotEmpty() ||
            volume != null || speechRate != null || fillerWords.isNotEmpty() ||
            designSegments.isNotEmpty() || typeDistribution.isNotEmpty() || introAnalysis != null ||
            conclusionAnalysis != null || infoDensity.isNotEmpty() ||
            wordCloud.isNotEmpty() || knowledgeTree.isNotEmpty() ||
            interactionEvents.isNotEmpty() || typeStatistics.isNotEmpty() || whSlices.isNotEmpty() ||
            ideologyEvents.isNotEmpty()

    companion object {
        private val WhOrder = listOf("若何", "是何", "为何", "如何", "由何")

        fun parse(element: JsonElement?, json: Json): VideoAnalysisResult {
            val root = (element as? JsonObject) ?: return VideoAnalysisResult()

            // ---- Legacy schema gate ----
            // V2 videos carry one of the new keys below; legacy videos carry the old keys and none
            // of the V2 keys. Detect legacy (any legacy key present AND no V2 key) and map it onto
            // the same display fields so pre-V2 videos still render their charts.
            val hasV2 = root.hasNonNull(
                "radar_data", "teaching_expression", "teaching_design",
                "knowledge_presentation", "interaction_quality", "ideological_integration",
            )
            val hasLegacy = root.hasNonNull(
                "teach_summary", "teach_db_result", "knowledge_graph", "teach_wh",
                "teach_question", "class_education_summary", "teach_knowledge",
            )
            if (hasLegacy && !hasV2) return parseLegacy(root, json)

            // 雷达图 / 综合得分: radar_data = [{dimension, score}]; the 综合得分 entry is the overall score.
            val radarAxes = mutableListOf<RadarAxis>()
            var overall: Int? = null
            for (item in (root.unwrap("radar_data", json) as? JsonArray).orEmpty()) {
                val obj = item as? JsonObject ?: continue
                val dimension = obj.stringOrEmpty("dimension")
                val score = obj.numberOrNull("score") ?: continue
                if (dimension == "综合得分") overall = score.roundToInt()
                else if (dimension.isNotEmpty()) radarAxes.add(RadarAxis(dimension, score))
            }
            // overall = radar 综合得分 ?? scores.overall ?? mean(axes).
            if (overall == null) {
                val scoresOverall = (root.unwrap("scores", json) as? JsonObject)?.numberOrNull("overall")
                if (scoresOverall != null) overall = scoresOverall.roundToInt()
            }
            if (overall == null && radarAxes.isNotEmpty()) {
                overall = (radarAxes.sumOf { it.value } / radarAxes.size).roundToInt()
            }

            // AI 总评 / 改进建议: ai_summary = { summary, suggestions } (or a bare string).
            val aiRaw = root.unwrap("ai_summary", json)
            val aiObj = aiRaw as? JsonObject
            val aiSummary = when {
                aiObj != null -> aiObj.stringOrEmpty("summary").takeIf { it.isNotEmpty() }
                aiRaw is JsonPrimitive && aiRaw.isString -> aiRaw.content.takeIf { it.isNotEmpty() }
                else -> null
            }
            val aiSuggestions = (aiObj?.get("suggestions") as? JsonArray).orEmpty()
                .mapNotNull { (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.content?.trim()?.takeIf { s -> s.isNotEmpty() } }

            // 教学表达: 语速 / 音量 series + 语言精炼度（口头禅）.
            val te = root.unwrap("teaching_expression", json) as? JsonObject
            val speechRate = metricSeries(te?.get("speech_rate_analysis") as? JsonObject, "avg_cpm", "max_cpm", "min_cpm", "CPM")
            val volume = metricSeries(te?.get("volume_analysis") as? JsonObject, "avg_spl", "max_spl", "min_spl", "dB")
            val conciseness = te?.get("language_conciseness") as? JsonObject
            val fillerRatio = conciseness?.numberOrNull("filler_word_ratio")
            val fillerCount = conciseness?.numberOrNull("filler_word_count")?.toInt()
            val fillerWords = (conciseness?.get("top_filler_words") as? JsonArray).orEmpty().mapNotNull { item ->
                val o = item as? JsonObject ?: return@mapNotNull null
                val term = o.stringOrEmpty("term").takeIf { it.isNotEmpty() } ?: return@mapNotNull null
                val examples = (o["examples"] as? JsonArray).orEmpty().mapNotNull { ex ->
                    val eo = ex as? JsonObject ?: return@mapNotNull null
                    val text = eo.stringOrEmpty("text").takeIf { it.isNotEmpty() } ?: return@mapNotNull null
                    FillerExample(time = eo.numberOrNull("start") ?: 0.0, text = text)
                }
                FillerWord(term = term, count = (o.numberOrNull("count") ?: 0.0).toInt(), examples = examples)
            }

            // 教学设计: 环节 segments、占比、导入/总结分析、信息密度.
            val td = root.unwrap("teaching_design", json) as? JsonObject
            val designSegments = (td?.get("segments") as? JsonArray).orEmpty().mapNotNull { item ->
                val o = item as? JsonObject ?: return@mapNotNull null
                TeachSegment(
                    type = o.stringOrEmpty("type"),
                    startTime = o.stringOrEmpty("start_time"),
                    endTime = o.stringOrEmpty("end_time"),
                    content = o.stringOrEmpty("content"),
                    keypoint = o.stringOrEmpty("keypoint_name"),
                )
            }
            val typeDistribution = (td?.get("type_distribution") as? JsonArray).orEmpty().mapNotNull { item ->
                val o = item as? JsonObject ?: return@mapNotNull null
                val type = o.stringOrEmpty("type").takeIf { it.isNotEmpty() } ?: return@mapNotNull null
                val duration = o.numberOrNull("duration_seconds") ?: 0.0
                val count = (o.numberOrNull("count") ?: 0.0).toInt()
                ChartSlice(type, if (duration > 0) duration.toInt() else count)
            }
            val introAnalysis = phaseAnalysis(td?.get("introduction_analysis") as? JsonObject)
            val conclusionAnalysis = phaseAnalysis(td?.get("conclusion_analysis") as? JsonObject)
            val infoDensity = ((td?.get("information_density") as? JsonObject)?.get("result") as? JsonArray)
                .orEmpty().mapNotNull { it.numberOrNull() }

            // 知识呈现: 词云（含权重）+ 知识树.
            val kp = root.unwrap("knowledge_presentation", json) as? JsonObject
            val wordCloud = (kp?.get("word_cloud") as? JsonArray).orEmpty().mapNotNull { item ->
                val o = item as? JsonObject ?: return@mapNotNull null
                val word = o.stringOrEmpty("word").takeIf { it.isNotEmpty() } ?: return@mapNotNull null
                WordWeight(word, (o.numberOrNull("weight") ?: 0.0).toInt())
            }
            val knowledgeTree = knowledgeNodes(kp?.get("knowledge_tree") as? JsonArray)

            // 互动质量: 事件时间轴、类型统计、五何分布.
            val iq = root.unwrap("interaction_quality", json) as? JsonObject
            val interactionEvents = (iq?.get("interaction_events") as? JsonArray).orEmpty().mapNotNull { item ->
                val o = item as? JsonObject ?: return@mapNotNull null
                val text = o.stringOrEmpty("text").takeIf { it.isNotEmpty() }
                    ?: o.stringOrEmpty("segment").takeIf { it.isNotEmpty() }
                    ?: return@mapNotNull null
                InteractionEvent(time = timeToSeconds(o.stringOrEmpty("start_time")), type = o.stringOrEmpty("type"), text = text)
            }
            val typeStatistics = (iq?.get("type_statistics") as? JsonObject).orEmpty()
                .mapNotNull { (k, v) ->
                    val n = (v.numberOrNull() ?: 0.0).toInt()
                    if (n > 0) ChartSlice(k, n) else null
                }
                .sortedByDescending { it.count }
            val whSlices = mutableListOf<ChartSlice>()
            val whObj = iq?.get("wh_distribution") as? JsonObject
            if (whObj != null) {
                for (key in WhOrder) {
                    val n = ((whObj[key] as? JsonObject)?.numberOrNull("count") ?: continue).toInt()
                    if (n > 0) whSlices.add(ChartSlice(key, n))
                }
                for ((k, v) in whObj) {
                    if (k in WhOrder) continue
                    val n = ((v as? JsonObject)?.numberOrNull("count") ?: continue).toInt()
                    if (n > 0) whSlices.add(ChartSlice(k, n))
                }
            }

            // 思政融合: 思政事件.
            val ii = root.unwrap("ideological_integration", json) as? JsonObject
            val ideologyEvents = (ii?.get("ideological_events") as? JsonArray).orEmpty().mapNotNull { item ->
                val o = item as? JsonObject ?: return@mapNotNull null
                val start = o.numberOrNull("start")
                val end = o.numberOrNull("end")
                val range = if (start != null || end != null) "${clock(start ?: 0.0)} - ${clock(end ?: 0.0)}" else ""
                IdeologyEvent(
                    title = o.stringOrEmpty("title").takeIf { it.isNotEmpty() } ?: "思政事件",
                    content = o.stringOrEmpty("content"),
                    score = (o.numberOrNull("integration_score") ?: 0.0).toInt(),
                    evaluation = o.stringOrEmpty("integration_evaluation"),
                    timeRange = range,
                )
            }

            return VideoAnalysisResult(
                radarAxes = radarAxes,
                overallScore = overall,
                aiSummary = aiSummary,
                aiSuggestions = aiSuggestions,
                speechRate = speechRate,
                volume = volume,
                fillerWords = fillerWords,
                fillerRatio = fillerRatio,
                fillerCount = fillerCount,
                designSegments = designSegments,
                typeDistribution = typeDistribution,
                introAnalysis = introAnalysis,
                conclusionAnalysis = conclusionAnalysis,
                infoDensity = infoDensity,
                wordCloud = wordCloud,
                knowledgeTree = knowledgeTree,
                interactionEvents = interactionEvents,
                typeStatistics = typeStatistics,
                whSlices = whSlices,
                ideologyEvents = ideologyEvents,
                audioDuration = volume?.totalDuration ?: speechRate?.totalDuration,
            )
        }

        /**
         * Legacy-schema parse — videos analyzed before the server's V2 migration stored the old
         * ResourceAnalysisReportView shape (teach_summary / teach_db_result / knowledge_graph /
         * teach_wh / teach_question / class_education_summary …). Mapped onto the same display
         * fields. Mirrors iOS `init(legacyContainer:)`. Every top-level lookup is unwrapped so a
         * JSON-encoded-string field is re-parsed before reading.
         */
        private fun parseLegacy(root: JsonObject, json: Json): VideoAnalysisResult {
            // 整体评价: legacy carries no radar in most cases; surface the course summary as 总评.
            val tsValue = root.unwrap("teach_summary", json)
            val summaryObj = (tsValue as? JsonArray)?.firstOrNull() as? JsonObject ?: tsValue as? JsonObject
            val aiSummary = summaryObj?.stringValue("summary") ?: summaryObj?.stringValue("text")
            val aiSuggestions = emptyList<String>()

            val axes = mutableListOf<RadarAxis>()
            var overall: Int? = null
            val rc = root.unwrap("radar_chart", json) as? JsonObject
            if (rc != null) {
                for (key in rc.keys.sorted()) {
                    val score = rc.numberOrNull(key) ?: continue
                    if (key == "综合得分") overall = score.roundToInt()
                    else axes.add(RadarAxis(key, score))
                }
            }
            if (overall == null && axes.isNotEmpty()) {
                overall = (axes.sumOf { it.value } / axes.size).roundToInt()
            }

            // 教学表达: teach_db_result.data.result is a 音量(dB) sample series.
            val dbResult = root.unwrap("teach_db_result", json) as? JsonObject
            val volSamples = ((dbResult?.get("data") as? JsonObject)?.get("result") as? JsonArray)
                .orEmpty().mapNotNull { it.numberOrNull() }
            val volume = if (volSamples.isEmpty()) null else MetricSeries(
                samples = volSamples,
                avg = volSamples.average(),
                max = volSamples.maxOrNull() ?: 0.0,
                min = volSamples.minOrNull() ?: 0.0,
                unit = "dB",
                totalDuration = null,
            )

            // 教学设计: teach_summary[].file_structure → 环节 segments + 类型占比.
            val segs = (summaryObj?.get("file_structure") as? JsonArray).orEmpty().mapNotNull { item ->
                val o = item as? JsonObject ?: return@mapNotNull null
                TeachSegment(
                    type = o.stringOrEmpty("type"),
                    startTime = o.stringOrEmpty("start_time"),
                    endTime = o.stringOrEmpty("end_time"),
                    content = o.stringOrEmpty("content"),
                    keypoint = o.stringOrEmpty("keypoint"),
                )
            }
            val typeOrder = mutableListOf<String>()
            val typeCount = mutableMapOf<String, Int>()
            for (s in segs) {
                if (s.type.isEmpty()) continue
                if (typeCount[s.type] == null) typeOrder.add(s.type)
                typeCount[s.type] = (typeCount[s.type] ?: 0) + 1
            }
            val typeDistribution = typeOrder.map { ChartSlice(it, typeCount[it] ?: 0) }

            // 知识呈现: teach_knowledge[].file_structure (title-based) → 知识树, else knowledge_graph (word-based).
            val tkStruct = ((root.unwrap("teach_knowledge", json) as? JsonArray)?.firstOrNull() as? JsonObject)
                ?.get("file_structure") as? JsonArray
            val tree: List<KnowledgeNode> = if (!tkStruct.isNullOrEmpty()) {
                knowledgeNodes(tkStruct)
            } else {
                val kg = ((root.unwrap("knowledge_graph", json) as? JsonObject)
                    ?.get("result") as? JsonObject)?.get("result") as? JsonArray
                legacyKnowledgeNodes(kg)
            }
            val wordCloud = wordCloudFromTree(tree)

            // 互动质量: teach_question 统计/事件 + teach_wh 五何分布.
            val tq = root.unwrap("teach_question", json) as? JsonObject
            val typeStatistics = (tq?.get("statistics") as? JsonObject).orEmpty()
                .mapNotNull { (key, value) ->
                    val n = ((value as? JsonObject)?.numberOrNull("count") ?: 0.0).toInt()
                    if (n > 0) ChartSlice(key, n) else null
                }
                .sortedByDescending { it.count }
            val interactionEvents = (tq?.get("questions") as? JsonArray).orEmpty().mapNotNull { item ->
                val o = item as? JsonObject ?: return@mapNotNull null
                val text = o.stringOrEmpty("text").takeIf { it.isNotEmpty() } ?: return@mapNotNull null
                InteractionEvent(
                    time = timeToSeconds(o.stringOrEmpty("start_time")),
                    type = o.stringOrEmpty("type"),
                    text = text,
                )
            }
            val whCount = mutableMapOf<String, Int>()
            for (item in (root.unwrap("teach_wh", json) as? JsonArray).orEmpty()) {
                val cat = (item as? JsonObject)?.stringValue("category")?.takeIf { it.isNotEmpty() } ?: continue
                whCount[cat] = (whCount[cat] ?: 0) + 1
            }
            val whSlices = mutableListOf<ChartSlice>()
            for (key in WhOrder) {
                if ((whCount[key] ?: 0) > 0) whSlices.add(ChartSlice(key, whCount[key] ?: 0))
            }
            for (key in whCount.keys.sorted()) {
                if (key in WhOrder) continue
                whSlices.add(ChartSlice(key, whCount[key] ?: 0))
            }

            // 思政融合: class_education_summary.summary[].result {title, content}.
            val ces = root.unwrap("class_education_summary", json) as? JsonObject
            val ideologyEvents = (ces?.get("summary") as? JsonArray).orEmpty().mapNotNull { item ->
                val o = item as? JsonObject ?: return@mapNotNull null
                val r = o["result"] as? JsonObject ?: return@mapNotNull null
                val content = r.stringOrEmpty("content").takeIf { it.isNotEmpty() } ?: return@mapNotNull null
                val start = o.numberOrNull("start")
                val end = o.numberOrNull("end")
                val range = if (start != null || end != null) "${clock(start ?: 0.0)} - ${clock(end ?: 0.0)}" else ""
                IdeologyEvent(
                    title = r.stringValue("title") ?: "思政融合",
                    content = content,
                    score = 0,
                    evaluation = "",
                    timeRange = range,
                )
            }

            val audioDuration = (root.unwrap("audio_duration", json))?.numberOrNull() ?: volume?.totalDuration

            return VideoAnalysisResult(
                radarAxes = axes,
                overallScore = overall,
                aiSummary = aiSummary,
                aiSuggestions = aiSuggestions,
                speechRate = null,
                volume = volume,
                fillerWords = emptyList(),
                fillerRatio = null,
                fillerCount = null,
                designSegments = segs,
                typeDistribution = typeDistribution,
                introAnalysis = null,
                conclusionAnalysis = null,
                infoDensity = emptyList(),
                wordCloud = wordCloud,
                knowledgeTree = tree,
                interactionEvents = interactionEvents,
                typeStatistics = typeStatistics,
                whSlices = whSlices,
                ideologyEvents = ideologyEvents,
                audioDuration = audioDuration,
            )
        }

        private fun metricSeries(obj: JsonObject?, avgKey: String, maxKey: String, minKey: String, unit: String): MetricSeries? {
            if (obj == null) return null
            val samples = (obj["result"] as? JsonArray).orEmpty().mapNotNull { it.numberOrNull() }
            if (samples.isEmpty()) return null
            return MetricSeries(
                samples = samples,
                avg = obj.numberOrNull(avgKey) ?: samples.average(),
                max = obj.numberOrNull(maxKey) ?: (samples.maxOrNull() ?: 0.0),
                min = obj.numberOrNull(minKey) ?: (samples.minOrNull() ?: 0.0),
                unit = unit,
                totalDuration = obj.numberOrNull("total_duration"),
            )
        }

        private fun phaseAnalysis(obj: JsonObject?): PhaseAnalysis? {
            if (obj.isNullOrEmpty()) return null
            return PhaseAnalysis(
                score = (obj.numberOrNull("score") ?: 0.0).toInt(),
                exists = (obj["exists"] as? JsonPrimitive)?.booleanOrNull ?: true,
                evaluation = obj.stringOrEmpty("evaluation"),
                timeRange = obj.stringOrEmpty("time_range"),
                description = obj.stringOrEmpty("description"),
            )
        }

        private fun knowledgeNodes(arr: JsonArray?): List<KnowledgeNode> =
            arr.orEmpty().mapNotNull { el ->
                val o = el as? JsonObject ?: return@mapNotNull null
                val title = o.stringOrEmpty("title").takeIf { it.isNotEmpty() } ?: return@mapNotNull null
                val start = o.stringOrEmpty("start_time")
                val end = o.stringOrEmpty("end_time")
                val range = if (start.isNotEmpty() || end.isNotEmpty()) "$start - $end" else ""
                KnowledgeNode(title, range, knowledgeNodes(o["children"] as? JsonArray))
            }

        /**
         * Legacy `knowledge_graph` nodes use `word` + `time_range:{start,end}` instead of the V2
         * `title` + `start_time`/`end_time`; map them onto the shared `KnowledgeNode` shape.
         */
        private fun legacyKnowledgeNodes(arr: JsonArray?): List<KnowledgeNode> =
            arr.orEmpty().mapNotNull { el ->
                val o = el as? JsonObject ?: return@mapNotNull null
                val word = o.stringValue("word") ?: o.stringValue("title") ?: return@mapNotNull null
                val tr = o["time_range"] as? JsonObject
                val start = tr?.stringValue("start") ?: o.stringValue("start_time") ?: ""
                val end = tr?.stringValue("end") ?: o.stringValue("end_time") ?: ""
                val range = if (start.isNotEmpty() || end.isNotEmpty()) "$start - $end" else ""
                KnowledgeNode(word, range, legacyKnowledgeNodes(o["children"] as? JsonArray))
            }

        /**
         * Derive a word cloud from a knowledge tree (legacy videos have no explicit cloud):
         * broader topics (more descendants) weigh more. Capped at 40 so the chart stays readable.
         */
        private fun wordCloudFromTree(nodes: List<KnowledgeNode>): List<WordWeight> {
            fun descendants(n: KnowledgeNode): Int = n.children.fold(n.children.size) { acc, c -> acc + descendants(c) }
            val out = mutableListOf<WordWeight>()
            fun walk(ns: List<KnowledgeNode>) {
                for (n in ns) {
                    if (n.title.isNotEmpty()) out.add(WordWeight(n.title, descendants(n) + 1))
                    walk(n.children)
                }
            }
            walk(nodes)
            return out.sortedByDescending { it.weight }.take(40)
        }

        private fun timeToSeconds(text: String): Double {
            val parts = text.split(':').mapNotNull { it.toDoubleOrNull() }
            if (parts.isEmpty()) return 0.0
            return parts.fold(0.0) { acc, x -> acc * 60 + x }
        }

        private fun clock(seconds: Double): String {
            val total = seconds.toInt()
            return "%d:%02d".format(total / 60, total % 60)
        }
    }
}

data class RadarAxis(val label: String, val value: Double)
data class ChartSlice(val label: String, val count: Int)
data class TeachSegment(val type: String, val startTime: String, val endTime: String, val content: String, val keypoint: String)
data class TeachSummarySection(val summary: String, val segments: List<TeachSegment>)
data class MetricSeries(val samples: List<Double>, val avg: Double, val max: Double, val min: Double, val unit: String, val totalDuration: Double?)
data class FillerExample(val time: Double, val text: String)
data class FillerWord(val term: String, val count: Int, val examples: List<FillerExample>)
data class PhaseAnalysis(val score: Int, val exists: Boolean, val evaluation: String, val timeRange: String, val description: String)
data class WordWeight(val word: String, val weight: Int)
data class KnowledgeNode(val title: String, val timeRange: String, val children: List<KnowledgeNode>)
data class InteractionEvent(val time: Double, val type: String, val text: String)
data class IdeologyEvent(val title: String, val content: String, val score: Int, val evaluation: String, val timeRange: String)

// ---- JsonElement helpers (local to this file) ----

/** iOS `JSONValue.stringValue`: the string content if a string primitive, else null (missing/non-string). */
private fun JsonObject.stringValue(key: String): String? =
    (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content

/** iOS `?.stringValue ?? ""`: string content if a string primitive, else "". */
private fun JsonObject.stringOrEmpty(key: String): String =
    (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content ?: ""

private fun JsonObject.numberOrNull(vararg keys: String): Double? {
    for (k in keys) {
        val v = this[k] as? JsonPrimitive ?: continue
        v.doubleOrNull?.let { return it }
        if (v.isString) v.content.toDoubleOrNull()?.let { return it }
    }
    return null
}

private fun JsonElement.numberOrNull(): Double? = when (this) {
    is JsonPrimitive -> doubleOrNull ?: if (isString) content.toDoubleOrNull() else null
    else -> null
}

/** True when at least one of [keys] is present and not JSON null (mirrors iOS `firstDecodable` presence). */
private fun JsonObject.hasNonNull(vararg keys: String): Boolean =
    keys.any { val v = this[it]; v != null && v != JsonNull }

/**
 * iOS `JSONValue.unwrappedJSON`: if a value is a JSON-encoded STRING, re-parse it into structured
 * JSON; otherwise return it unchanged. Applied at every top-level lookup in both V2 and legacy.
 */
private fun JsonObject.unwrap(key: String, json: Json): JsonElement? {
    val value = this[key] ?: return null
    if (value !is JsonPrimitive || !value.isString) return value
    return try {
        json.parseToJsonElement(value.content)
    } catch (e: Exception) {
        value
    }
}
