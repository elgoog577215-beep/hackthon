package com.mentorai.app.support

import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.concurrent.TimeUnit

/**
 * Mirrors the iOS `ServerDate` helper. The backend formats every `create_time` / `update_time`
 * as Asia/Shanghai wall-clock "yyyy-MM-dd HH:mm:ss" (see server common/utils/datetime.py).
 * `parse` accepts that primary shape and falls back to ISO 8601.
 */
object ServerDate {

    private val primary: SimpleDateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).apply {
        timeZone = TimeZone.getTimeZone("Asia/Shanghai")
        isLenient = false
    }

    private val iso: SimpleDateFormat = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US).apply {
        timeZone = TimeZone.getTimeZone("UTC")
        isLenient = true
    }

    private val isoFractional: SimpleDateFormat = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", Locale.US).apply {
        timeZone = TimeZone.getTimeZone("UTC")
        isLenient = true
    }

    private val timeOnly: SimpleDateFormat get() = SimpleDateFormat("HH:mm", Locale.CHINA)
    private val monthDay: SimpleDateFormat get() = SimpleDateFormat("M月d日", Locale.CHINA)
    private val yearMonthDay: SimpleDateFormat get() = SimpleDateFormat("yyyy年M月d日", Locale.CHINA)
    private val yearMonthDayTime: SimpleDateFormat get() = SimpleDateFormat("yyyy年M月d日 HH:mm", Locale.CHINA)

    fun parse(raw: String): Date? {
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) return null
        return try { primary.parse(trimmed) } catch (_: Exception) { null }
            ?: try { iso.parse(trimmed) } catch (_: Exception) { null }
            ?: try { isoFractional.parse(trimmed) } catch (_: Exception) { null }
    }

    /** Compact relative label for list rows. Returns the raw string unchanged when unparseable. */
    fun relative(raw: String, now: Date = Date()): String {
        val date = parse(raw) ?: return raw
        val seconds = TimeUnit.MILLISECONDS.toSeconds(now.time - date.time)
        if (seconds < 60) return "刚刚"

        val nowCal = Calendar.getInstance().apply { time = now }
        val thenCal = Calendar.getInstance().apply { time = date }
        val sameDay = nowCal.get(Calendar.YEAR) == thenCal.get(Calendar.YEAR) &&
            nowCal.get(Calendar.DAY_OF_YEAR) == thenCal.get(Calendar.DAY_OF_YEAR)
        if (sameDay) {
            if (seconds < 3600) return "${seconds / 60}分钟前"
            return "${seconds / 3600}小时前"
        }

        val yesterdayCal = (nowCal.clone() as Calendar).apply { add(Calendar.DAY_OF_YEAR, -1) }
        val isYesterday = yesterdayCal.get(Calendar.YEAR) == thenCal.get(Calendar.YEAR) &&
            yesterdayCal.get(Calendar.DAY_OF_YEAR) == thenCal.get(Calendar.DAY_OF_YEAR)
        if (isYesterday) return "昨天 " + timeOnly.format(date)

        if (nowCal.get(Calendar.YEAR) == thenCal.get(Calendar.YEAR)) return monthDay.format(date)
        return yearMonthDay.format(date)
    }

    /** Absolute label (used for stable values like registration time). */
    fun absolute(raw: String): String? {
        if (raw.isBlank()) return null
        val date = parse(raw) ?: return raw
        return yearMonthDayTime.format(date)
    }
}
