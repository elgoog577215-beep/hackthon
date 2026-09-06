import Foundation

/// Parses and formats the timestamps the backend emits. The server formats every
/// `create_time` / `update_time` as Asia/Shanghai wall-clock `"yyyy-MM-dd HH:mm:ss"`
/// (see server `common/utils/datetime.py`), which is *not* valid ISO 8601 — so a
/// plain ISO8601DateFormatter silently fails on it. We parse that shape first and
/// fall back to ISO 8601 for any endpoint that differs.
enum ServerDate {
    private static let primary: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "Asia/Shanghai")
        f.dateFormat = "yyyy-MM-dd HH:mm:ss"
        return f
    }()

    private static let iso = ISO8601DateFormatter()
    private static let isoFractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    static func parse(_ raw: String) -> Date? {
        let trimmed = raw.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return nil }
        return primary.date(from: trimmed)
            ?? iso.date(from: trimmed)
            ?? isoFractional.date(from: trimmed)
    }

    /// Compact relative label for list rows. Returns the raw string unchanged when unparseable.
    static func relative(_ raw: String, now: Date = Date()) -> String {
        guard let date = parse(raw) else { return raw }
        let seconds = now.timeIntervalSince(date)
        if seconds < 60 { return "刚刚" }

        let calendar = Calendar.current
        if calendar.isDateInToday(date) {
            if seconds < 3600 { return "\(Int(seconds / 60))分钟前" }
            return "\(Int(seconds / 3600))小时前"
        }
        if calendar.isDateInYesterday(date) {
            return "昨天 " + timeOnly.string(from: date)
        }
        if calendar.isDate(date, equalTo: now, toGranularity: .year) {
            return monthDay.string(from: date)
        }
        return yearMonthDay.string(from: date)
    }

    /// Absolute label (used for stable values like registration time).
    static func absolute(_ raw: String) -> String? {
        guard !raw.isEmpty else { return nil }
        guard let date = parse(raw) else { return raw }
        return yearMonthDayTime.string(from: date)
    }

    private static let timeOnly = display("HH:mm")
    private static let monthDay = display("M月d日")
    private static let yearMonthDay = display("yyyy年M月d日")
    private static let yearMonthDayTime = display("yyyy年M月d日 HH:mm")

    private static func display(_ format: String) -> DateFormatter {
        let f = DateFormatter()
        f.locale = Locale(identifier: "zh_CN")
        f.calendar = Calendar(identifier: .gregorian)
        f.dateFormat = format
        return f
    }
}
