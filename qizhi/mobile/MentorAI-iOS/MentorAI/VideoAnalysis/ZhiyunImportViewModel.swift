import Foundation
import os

@MainActor
final class ZhiyunImportViewModel: ObservableObject {
    // Search-only now: the actual import runs on `VideoListViewModel` (so it survives this
    // sheet closing — foreground-continue). This VM just finds courses for the user to pick.
    enum Phase: Equatable {
        case idle
        case searching
        case picking(courses: [ZhiyunCourse])
        case failed(String)
    }

    @Published private(set) var phase: Phase = .idle
    @Published var beginDate: Date
    @Published var endDate: Date
    @Published var courseNameFilter: String = ""

    private let api: VideoAPI
    private let tokenProvider: () -> String?
    private let log = Logger(subsystem: "com.mentorai.app", category: "ZhiyunImport")

    private static let dateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.timeZone = TimeZone.current
        return f
    }()

    init(api: VideoAPI, tokenProvider: @escaping () -> String?) {
        self.api = api
        self.tokenProvider = tokenProvider
        let cal = Calendar.current
        self.endDate = Date()
        self.beginDate = cal.date(byAdding: .day, value: -7, to: Date()) ?? Date()
    }

    func searchCourses() async {
        guard let token = tokenProvider(), !token.isEmpty else {
            phase = .failed("未登录")
            return
        }
        phase = .searching
        let begin = Self.dateFormatter.string(from: beginDate)
        let end = Self.dateFormatter.string(from: endDate)
        do {
            let list = try await api.listZhiyunCourses(
                beginDate: begin,
                endDate: end,
                courseName: courseNameFilter,
                token: token
            )
            phase = .picking(courses: list)
            log.info("Zhiyun returned \(list.count) courses")
        } catch let err as AuthError {
            phase = .failed(err.errorDescription ?? "查询失败")
        } catch {
            phase = .failed(error.localizedDescription)
        }
    }
}
