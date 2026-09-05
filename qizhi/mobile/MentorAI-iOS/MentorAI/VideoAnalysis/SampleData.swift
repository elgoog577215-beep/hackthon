#if DEBUG
import Foundation

/// DEBUG-only fixtures for exercising views without a backend. Compiled out of release builds.
enum SampleData {
    /// Decodes a bundled JSON fixture from the app bundle.
    /// Fails loudly (DEBUG-only) so a malformed fixture surfaces immediately during UI testing.
    static func load<T: Decodable>(_ type: T.Type, from name: String) -> T {
        guard let url = Bundle.main.url(forResource: name, withExtension: "json") else {
            fatalError("Sample fixture \(name).json is missing from the bundle. Run `xcodegen generate`.")
        }
        do {
            return try JSONDecoder().decode(T.self, from: Data(contentsOf: url))
        } catch {
            fatalError("Failed to decode \(name).json: \(error)")
        }
    }
}

extension VideoDetail {
    /// Fully-populated sample used to preview `VideoAnalysisDetailView` without a backend.
    static var sample: VideoDetail { SampleData.load(VideoDetail.self, from: "SampleVideoDetail") }
}
#endif
