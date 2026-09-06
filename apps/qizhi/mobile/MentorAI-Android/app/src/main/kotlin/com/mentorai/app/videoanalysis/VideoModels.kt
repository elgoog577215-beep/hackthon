@file:OptIn(ExperimentalSerializationApi::class)

package com.mentorai.app.videoanalysis

import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNames

/**
 * Wire models for the video-analysis module. Mirrors the iOS `VideoModels.swift` types.
 * Field-name aliases use @SerialName (canonical wire key) + @JsonNames (accepted aliases);
 * loose fields (JSON shape varies) keep `JsonElement` and are interpreted by
 * `VideoAnalysisResult.parse()` in a separate file.
 */

@Serializable
enum class VideoStatus {
    @SerialName("unstarted") Unstarted,
    @SerialName("waiting") Waiting,
    @SerialName("success") Success,
    @SerialName("failed") Failed;

    val displayLabel: String get() = when (this) {
        Unstarted -> "未开始分析"
        Waiting -> "分析中"
        Success -> "已完成"
        Failed -> "分析失败"
    }
}

/**
 * `operation` raw values must stay lowercase to match the server's `OperationEnum` —
 * this is the bug that bit the iOS app (see VideoModels.swift); preserving that lesson here.
 */
@Serializable
enum class VideoOperation {
    @SerialName("create") Create,
    @SerialName("update") Update,
    @SerialName("delete") Delete,
}

/**
 * 视频分析方式。`cloud`=智云课堂(超星)云端分析（默认）；`local`=本地自建模型直接分析。
 * Mirrors the iOS `AnalysisMode` (`VideoAPI.swift`) and web `AnalysisMode` (`api/video.ts`);
 * sent as the `mode` query param to `/video/analyze` via [wireValue].
 */
@Serializable
enum class AnalysisMode {
    @SerialName("cloud") Cloud,
    @SerialName("local") Local;

    /** Lowercase wire value used as the `mode` query param (matches iOS `rawValue`). */
    val wireValue: String get() = when (this) {
        Cloud -> "cloud"
        Local -> "local"
    }
}

@Serializable
data class VideoSummary(
    val id: String = "",
    val name: String = "未命名视频",
    val status: VideoStatus = VideoStatus.Unstarted,
    val cover: String? = null,
    @SerialName("analysis_start_time") @JsonNames("analysisStartTime") val analysisStartTime: String? = null,
    @SerialName("create_time") @JsonNames("createTime") val createTime: String = "",
    /** 本地分析预估剩余秒数（仅本地分析「分析中」、含排队；云端分析为 null）。 */
    @SerialName("estimated_seconds") @JsonNames("estimatedSeconds") val estimatedSeconds: Int? = null,
)

@Serializable
data class VideoOperationRequest(
    val operation: VideoOperation,
    val id: String? = null,
    val name: String? = null,
    val path: String? = null,
    val cover: String? = null,
)

@Serializable
data class VideoDetail(
    val id: String = "",
    val name: String = "未命名视频",
    val path: String = "",
    val status: VideoStatus = VideoStatus.Unstarted,
    @SerialName("analysis_start_time") @JsonNames("analysisStartTime") val analysisStartTime: String? = null,
    @SerialName("analysis_result") @JsonNames("analysisResult") val analysisResult: JsonElement? = null,
    @SerialName("create_time") @JsonNames("createTime") val createTime: String = "",
)

// ---- Zhiyun (smart classroom) — server returns groups; we flatten on the client. ----

@Serializable
data class ZhiyunCourseItem(
    @SerialName("sub_id") @JsonNames("subId") val subId: String = "",
    @SerialName("sub_title") @JsonNames("subTitle", "subtitle") val subTitle: String = "",
    @SerialName("teacher_name") @JsonNames("teacherName") val teacherName: String = "",
    @SerialName("class_begin") @JsonNames("classBegin") val classBegin: String = "",
)

@Serializable
data class ZhiyunCourseGroup(
    @SerialName("course_id") @JsonNames("courseId") val courseId: String = "",
    @SerialName("course_name") @JsonNames("courseName") val courseName: String = "未命名课程",
    val items: List<ZhiyunCourseItem> = emptyList(),
)

/** Flattened recording row shown in the import picker. Mirrors iOS `ZhiyunCourse`. */
data class ZhiyunCourse(
    val courseId: String,
    val subId: String,
    val courseName: String,
    val subTitle: String,
    val teacherName: String,
    val classBegin: String,
) {
    val id: String get() = "$courseId#$subId"
}

// ---- Upload helpers ----

/** Returned by `/video/finish` — mirrors iOS `VideoAPI.UploadFinishResult`. */
data class UploadFinishResult(val videoPath: String, val coverPath: String?)
