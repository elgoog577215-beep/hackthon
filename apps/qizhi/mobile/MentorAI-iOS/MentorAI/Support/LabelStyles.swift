import SwiftUI

/// Label style with a small, fixed icon-to-title gap. SwiftUI's default `Label` spacing
/// looks too airy for compact inline metadata (icon + short text), so use this for chips
/// and metadata rows. Matches the app's other inline icon+text rows (HStack spacing 4).
struct TightLabelStyle: LabelStyle {
    var spacing: CGFloat = 4

    func makeBody(configuration: Configuration) -> some View {
        HStack(spacing: spacing) {
            configuration.icon
            configuration.title
        }
    }
}

extension LabelStyle where Self == TightLabelStyle {
    static var tight: TightLabelStyle { TightLabelStyle() }
}
