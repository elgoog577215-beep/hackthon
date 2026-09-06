import SwiftUI

// Colors mirror the web report (primary #5B8DEE, average line #e8b84d).
enum ReportPalette {
    static let primary = Color(red: 0x5B / 255, green: 0x8D / 255, blue: 0xEE / 255)
    static let average = Color(red: 0xE8 / 255, green: 0xB8 / 255, blue: 0x4D / 255)
    static let series: [Color] = [
        Color(red: 0x5B / 255, green: 0x8D / 255, blue: 0xEE / 255),
        Color(red: 0x67 / 255, green: 0xC2 / 255, blue: 0x3A / 255),
        Color(red: 0xE8 / 255, green: 0xB8 / 255, blue: 0x4D / 255),
        Color(red: 0xE3 / 255, green: 0x6B / 255, blue: 0x6B / 255),
        Color(red: 0x9B / 255, green: 0x7B / 255, blue: 0xEA / 255),
        Color(red: 0x4D / 255, green: 0xBF / 255, blue: 0xB5 / 255),
        Color(red: 0xF0 / 255, green: 0x9B / 255, blue: 0x59 / 255),
    ]

    static func color(_ index: Int) -> Color {
        series[index % series.count]
    }
}

/// Wrapping layout used by the donut legends and the knowledge tag cloud.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout Void) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        let rows = arrange(subviews: subviews, maxWidth: maxWidth)
        let height = rows.reduce(0) { $0 + $1.height } + CGFloat(max(0, rows.count - 1)) * spacing
        let width = rows.map(\.width).max() ?? 0
        return CGSize(width: maxWidth.isFinite ? maxWidth : width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout Void) {
        let rows = arrange(subviews: subviews, maxWidth: bounds.width)
        var y = bounds.minY
        for row in rows {
            var x = bounds.minX
            for index in row.indices {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(at: CGPoint(x: x, y: y), anchor: .topLeading, proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
            y += row.height + spacing
        }
    }

    private struct Row {
        var indices: [Int] = []
        var width: CGFloat = 0
        var height: CGFloat = 0
    }

    private func arrange(subviews: Subviews, maxWidth: CGFloat) -> [Row] {
        var rows: [Row] = []
        var row = Row()
        var x: CGFloat = 0
        for index in subviews.indices {
            let size = subviews[index].sizeThatFits(.unspecified)
            if x + size.width > maxWidth, !row.indices.isEmpty {
                rows.append(row)
                row = Row()
                x = 0
            }
            row.indices.append(index)
            x += size.width + spacing
            row.width = max(row.width, x - spacing)
            row.height = max(row.height, size.height)
        }
        if !row.indices.isEmpty { rows.append(row) }
        return rows
    }
}

/// 雷达图 — six teaching-performance axes scored 0...100.
/// Tap an axis to select it: its vertex enlarges, its label/score emphasize, and the
/// centre shows that axis's score.
struct RadarChartView: View {
    let axes: [RadarAxis]
    @State private var selectedIndex: Int?
    private let maxScore: Double = 100

    var body: some View {
        GeometryReader { geo in
            let center = CGPoint(x: geo.size.width / 2, y: geo.size.height / 2)
            let radius = min(geo.size.width, geo.size.height) / 2 - 46
            ZStack {
                Canvas { context, _ in
                    let count = axes.count
                    guard count >= 3 else { return }

                    func vertex(fraction: Double, index: Int) -> CGPoint {
                        let angle = -Double.pi / 2 + Double(index) * 2 * .pi / Double(count)
                        return CGPoint(
                            x: center.x + CGFloat(cos(angle) * Double(radius) * fraction),
                            y: center.y + CGFloat(sin(angle) * Double(radius) * fraction)
                        )
                    }

                    for level in 1...5 {
                        var grid = Path()
                        let fraction = Double(level) / 5
                        for index in 0..<count {
                            let point = vertex(fraction: fraction, index: index)
                            if index == 0 { grid.move(to: point) } else { grid.addLine(to: point) }
                        }
                        grid.closeSubpath()
                        context.stroke(grid, with: .color(.gray.opacity(0.22)), lineWidth: 1)
                    }

                    for index in 0..<count {
                        var spoke = Path()
                        spoke.move(to: center)
                        spoke.addLine(to: vertex(fraction: 1, index: index))
                        let selected = selectedIndex == index
                        context.stroke(
                            spoke,
                            with: .color(selected ? ReportPalette.primary.opacity(0.5) : .gray.opacity(0.18)),
                            lineWidth: selected ? 1.5 : 1
                        )
                    }

                    var shape = Path()
                    for index in 0..<count {
                        let fraction = min(1, max(0, axes[index].value / maxScore))
                        let point = vertex(fraction: fraction, index: index)
                        if index == 0 { shape.move(to: point) } else { shape.addLine(to: point) }
                    }
                    shape.closeSubpath()
                    context.fill(shape, with: .color(ReportPalette.primary.opacity(0.28)))
                    context.stroke(shape, with: .color(ReportPalette.primary), lineWidth: 2)

                    for index in 0..<count {
                        let selected = selectedIndex == index
                        let fraction = min(1, max(0, axes[index].value / maxScore))
                        let point = vertex(fraction: fraction, index: index)
                        let r: CGFloat = selected ? 5 : 3
                        context.fill(Path(ellipseIn: CGRect(x: point.x - r, y: point.y - r, width: r * 2, height: r * 2)),
                                     with: .color(ReportPalette.primary))

                        let labelPoint = vertex(fraction: 1.2, index: index)
                        context.draw(
                            Text(axes[index].label).font(selected ? .caption2.bold() : .caption2)
                                .foregroundColor(selected ? ReportPalette.primary : .secondary),
                            at: labelPoint, anchor: .center
                        )
                        context.draw(
                            Text(String(format: "%.0f", axes[index].value)).font(.caption2.bold())
                                .foregroundColor(selected ? ReportPalette.primary : .primary),
                            at: CGPoint(x: labelPoint.x, y: labelPoint.y + 13), anchor: .center
                        )
                    }
                }
                if let index = selectedIndex, axes.indices.contains(index) {
                    VStack(spacing: 2) {
                        Text(axes[index].label).font(.caption).foregroundStyle(.secondary)
                        Text("\(Int(axes[index].value.rounded())) 分").font(.title3.weight(.semibold))
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(.ultraThinMaterial, in: Capsule())
                    .transition(.opacity)
                }
            }
            .contentShape(Rectangle())
            .simultaneousGesture(
                DragGesture(minimumDistance: 0).onEnded { value in
                    let moved = hypot(value.translation.width, value.translation.height)
                    guard moved < 10 else { return }
                    let hit = axisIndex(at: value.location, center: center)
                    withAnimation(.easeOut(duration: 0.15)) {
                        selectedIndex = (hit == selectedIndex) ? nil : hit
                    }
                }
            )
        }
        .frame(height: 280)
    }

    private func axisIndex(at point: CGPoint, center: CGPoint) -> Int? {
        let dx = Double(point.x - center.x)
        let dy = Double(point.y - center.y)
        guard hypot(dx, dy) > 16 else { return nil }
        let count = axes.count
        guard count >= 3 else { return nil }
        let tapAngle = atan2(dy, dx)
        var best = 0
        var bestDelta = Double.infinity
        for index in 0..<count {
            let axisAngle = -Double.pi / 2 + Double(index) * 2 * .pi / Double(count)
            let delta = abs(angleDifference(tapAngle, axisAngle))
            if delta < bestDelta { bestDelta = delta; best = index }
        }
        return best
    }

    private func angleDifference(_ a: Double, _ b: Double) -> Double {
        var d = (a - b).truncatingRemainder(dividingBy: 2 * .pi)
        if d > .pi { d -= 2 * .pi } else if d < -.pi { d += 2 * .pi }
        return d
    }
}

/// Interactive ring chart reused for 五何互动交流 and 课堂环节占比.
/// Tap a slice (or a legend chip) to select it: the slice pops out, the rest dim,
/// and the centre shows that slice's label, count and share.
struct DonutChartView: View {
    let slices: [ChartSlice]
    @State private var selectedIndex: Int?

    private let ringWidth: CGFloat = 26

    private var total: Int { max(1, slices.reduce(0) { $0 + $1.count }) }

    private func percent(_ count: Int) -> Int {
        Int((Double(count) / Double(total) * 100).rounded())
    }

    var body: some View {
        VStack(spacing: 14) {
            GeometryReader { geo in
                let radius = min(geo.size.width, geo.size.height) / 2 - ringWidth / 2 - 6
                let center = CGPoint(x: geo.size.width / 2, y: geo.size.height / 2)
                ZStack {
                    ring(center: center, radius: radius)
                    if let index = selectedIndex, slices.indices.contains(index) {
                        VStack(spacing: 2) {
                            Text(slices[index].label)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text("\(percent(slices[index].count))%")
                                .font(.title3.weight(.semibold))
                        }
                        .transition(.opacity)
                    }
                }
                .contentShape(Rectangle())
                .simultaneousGesture(
                    DragGesture(minimumDistance: 0).onEnded { value in
                        let moved = hypot(value.translation.width, value.translation.height)
                        guard moved < 10 else { return }
                        let hit = sliceIndex(at: value.location, center: center, radius: radius)
                        withAnimation(.easeOut(duration: 0.15)) {
                            selectedIndex = (hit == selectedIndex) ? nil : hit
                        }
                    }
                )
            }
            .frame(height: 184)

            FlowLayout(spacing: 10) {
                ForEach(Array(slices.enumerated()), id: \.element.id) { index, slice in
                    Button {
                        withAnimation(.easeOut(duration: 0.15)) {
                            selectedIndex = (selectedIndex == index) ? nil : index
                        }
                    } label: {
                        HStack(spacing: 5) {
                            Circle().fill(ReportPalette.color(index)).frame(width: 8, height: 8)
                            Text("\(slice.label) \(percent(slice.count))%")
                                .font(.caption2)
                                .fontWeight(selectedIndex == index ? .semibold : .regular)
                                .foregroundStyle(selectedIndex == index ? Color.primary : Color.secondary)
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private func ring(center: CGPoint, radius: CGFloat) -> some View {
        Canvas { context, _ in
            let track = Path(ellipseIn: CGRect(
                x: center.x - radius, y: center.y - radius, width: radius * 2, height: radius * 2
            ))
            context.stroke(track, with: .color(.gray.opacity(0.12)), lineWidth: ringWidth)

            var start = Angle.degrees(-90)
            for (index, slice) in slices.enumerated() {
                let sweep = Double(slice.count) / Double(total) * 360
                let end = start + .degrees(sweep)
                let selected = selectedIndex == index
                let dimmed = selectedIndex != nil && !selected
                var arc = Path()
                arc.addArc(center: center, radius: radius, startAngle: start, endAngle: end, clockwise: false)
                context.stroke(
                    arc,
                    with: .color(ReportPalette.color(index).opacity(dimmed ? 0.35 : 1)),
                    style: StrokeStyle(lineWidth: selected ? ringWidth + 8 : ringWidth, lineCap: .butt)
                )
                start = end
            }
        }
    }

    private func sliceIndex(at point: CGPoint, center: CGPoint, radius: CGFloat) -> Int? {
        let dx = point.x - center.x
        let dy = point.y - center.y
        let distance = hypot(dx, dy)
        guard distance >= radius - ringWidth / 2 - 12, distance <= radius + ringWidth / 2 + 12 else { return nil }
        var angle = Double(atan2(dy, dx)) + .pi / 2
        if angle < 0 { angle += 2 * .pi }
        let fraction = angle / (2 * .pi)
        var cumulative = 0.0
        for (index, slice) in slices.enumerated() {
            let sliceFraction = Double(slice.count) / Double(total)
            if fraction >= cumulative, fraction < cumulative + sliceFraction {
                return index
            }
            cumulative += sliceFraction
        }
        return nil
    }
}

/// Interactive per-window line chart reused for 语速 (CPM) / 音量 (dB) / 信息密度.
/// Tap or scrub horizontally to inspect a point's time and value; vertical scrolls pass through.
struct MetricLineChart: View {
    let title: String
    let samples: [Double]
    var unit: String = ""
    var fractionDigits: Int = 0
    var totalDuration: Double? = nil
    var statsAvg: Double? = nil
    var statsMax: Double? = nil
    var statsMin: Double? = nil
    @State private var selectedIndex: Int?

    var body: some View {
        let lo = samples.min() ?? 0
        let hi = samples.max() ?? 1
        let range = max(0.0001, hi - lo)
        let average = statsAvg ?? (samples.isEmpty ? 0 : samples.reduce(0, +) / Double(samples.count))
        let shownMax = statsMax ?? hi
        let shownMin = statsMin ?? lo

        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(title).font(.caption.weight(.medium))
                Spacer()
                if let index = selectedIndex, samples.indices.contains(index) {
                    Text("\(timeLabel(index)) · \(format(samples[index]))\(unitSuffix)")
                        .font(.caption2)
                        .foregroundStyle(ReportPalette.primary)
                } else {
                    Text("平均 \(format(average)) · 高 \(format(shownMax)) · 低 \(format(shownMin))")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            GeometryReader { geo in
                let size = geo.size
                Canvas { context, _ in
                    guard samples.count > 1 else { return }

                    func point(_ index: Int) -> CGPoint {
                        let x = size.width * CGFloat(index) / CGFloat(samples.count - 1)
                        let normalized = (samples[index] - lo) / range
                        return CGPoint(x: x, y: size.height - CGFloat(normalized) * size.height)
                    }

                    for fraction in [0.0, 0.5, 1.0] {
                        var grid = Path()
                        let y = size.height * CGFloat(fraction)
                        grid.move(to: CGPoint(x: 0, y: y))
                        grid.addLine(to: CGPoint(x: size.width, y: y))
                        context.stroke(grid, with: .color(.gray.opacity(0.1)), lineWidth: 1)
                    }

                    var line = Path()
                    for index in samples.indices {
                        let p = point(index)
                        if index == 0 { line.move(to: p) } else { line.addLine(to: p) }
                    }
                    context.stroke(line, with: .color(ReportPalette.primary), style: StrokeStyle(lineWidth: 2, lineJoin: .round))

                    let averageNormalized = (average - lo) / range
                    let averageY = size.height - CGFloat(averageNormalized) * size.height
                    var averageLine = Path()
                    averageLine.move(to: CGPoint(x: 0, y: averageY))
                    averageLine.addLine(to: CGPoint(x: size.width, y: averageY))
                    context.stroke(averageLine, with: .color(ReportPalette.average), style: StrokeStyle(lineWidth: 1.5, dash: [5, 5]))

                    if let index = selectedIndex, samples.indices.contains(index) {
                        let p = point(index)
                        var marker = Path()
                        marker.move(to: CGPoint(x: p.x, y: 0))
                        marker.addLine(to: CGPoint(x: p.x, y: size.height))
                        context.stroke(marker, with: .color(ReportPalette.primary.opacity(0.4)), lineWidth: 1)
                        context.fill(Path(ellipseIn: CGRect(x: p.x - 4, y: p.y - 4, width: 8, height: 8)), with: .color(ReportPalette.primary))
                    }
                }
                .contentShape(Rectangle())
                .simultaneousGesture(
                    DragGesture(minimumDistance: 0).onChanged { value in
                        let dx = abs(value.translation.width), dy = abs(value.translation.height)
                        // Inspect on a tap or a mostly-horizontal scrub; let vertical scrolls pass.
                        guard dx >= dy || (dx < 8 && dy < 8) else { return }
                        guard samples.count > 1, size.width > 0 else { return }
                        let ratio = min(max(value.location.x / size.width, 0), 1)
                        selectedIndex = Int((ratio * CGFloat(samples.count - 1)).rounded())
                    }
                )
            }
            .frame(height: 150)
        }
    }

    private var unitSuffix: String { unit.isEmpty ? "" : " \(unit)" }
    private func format(_ v: Double) -> String { String(format: "%.\(fractionDigits)f", v) }
    private func timeLabel(_ index: Int) -> String {
        if let duration = totalDuration, duration > 0, samples.count > 1 {
            return ReportFormat.clock(duration * Double(index) / Double(samples.count - 1))
        }
        return "#\(index + 1)"
    }
}

/// 知识点词云 — Archimedean-spiral word cloud built from teach_knowledge titles.
/// Mirrors the web report: extract 2–6 char hot-word phrases, size by frequency,
/// then place largest-first along a spiral using an occupancy grid to avoid overlaps.
struct WordCloudView: View {
    private let placed: [PlacedWord]
    private static let canvas: CGFloat = 520

    /// Build a cloud from raw titles (frequency derived by tokenizing).
    init(titles: [String]) {
        self.placed = WordCloudView.place(WordCloudView.countTokens(titles))
    }

    /// Build a cloud from backend-weighted words (`word_cloud: [{word, weight}]`).
    init(words: [(String, Int)]) {
        self.placed = WordCloudView.place(words.map { (text: $0.0, count: $0.1) })
    }

    var body: some View {
        if placed.isEmpty {
            Text("暂无数据").font(.footnote).foregroundStyle(.secondary)
        } else {
            Canvas { context, size in
                let scale = size.width / WordCloudView.canvas
                for word in placed {
                    let text = Text(word.text)
                        .font(.system(size: word.size * scale, weight: word.weight))
                        .foregroundColor(word.color)
                    context.draw(text, at: CGPoint(x: word.center.x * scale, y: word.center.y * scale), anchor: .center)
                }
            }
            .frame(maxWidth: .infinity)
            .aspectRatio(1, contentMode: .fit)
        }
    }

    private struct PlacedWord {
        let text: String
        let size: CGFloat
        let weight: Font.Weight
        let color: Color
        let center: CGPoint
    }

    private static let palette: [Color] = [
        0x1358E4, 0x5B8DEE, 0xE06B5A, 0xF2B84B, 0x5FD3B3, 0x6B5FE3, 0xF28ADC,
        0x4BC0C0, 0xFFA07A, 0x20B2AA, 0x9370DB, 0xFFB347, 0xA0D468, 0xE7C14A,
    ].map { Color(hex: $0) }

    private static let separators = CharacterSet(charactersIn: "的与和到在及对为以其等了是有、，。·？！：；,.?!:;()（）")
        .union(.whitespacesAndNewlines)

    /// Tokenize titles into 2–6 char Chinese (or 1–8 char ASCII) hot-word phrases with counts.
    private static func countTokens(_ titles: [String]) -> [(text: String, count: Int)] {
        var counts: [String: Int] = [:]
        var order: [String] = []
        for title in titles {
            for part in title.components(separatedBy: separators) {
                let token = part.trimmingCharacters(in: .whitespaces)
                guard !token.isEmpty else { continue }
                let isChinese = token.unicodeScalars.contains { $0.value > 127 }
                let length = token.count
                if isChinese {
                    if length < 2 || length > 6 { continue }
                } else if length < 1 || length > 8 {
                    continue
                }
                if counts[token] == nil { order.append(token) }
                counts[token, default: 0] += 1
            }
        }
        return order.map { (text: $0, count: counts[$0]!) }
    }

    /// Size largest-first by count, then place along an Archimedean spiral with an occupancy grid.
    private static func place(_ rawWords: [(text: String, count: Int)]) -> [PlacedWord] {
        let words = Array(rawWords.sorted { $0.count > $1.count }.prefix(50))
        guard !words.isEmpty else { return [] }

        // 2) Size, weight and color by frequency.
        let maxCount = words.first?.count ?? 1
        let minCount = words.last?.count ?? 1
        let span = Double(max(1, maxCount - minCount))
        struct Sized { let text: String; let size: CGFloat; let weight: Font.Weight; let color: Color }
        let sized: [Sized] = words.enumerated().map { index, word in
            let norm = Double(word.count - minCount) / span
            let size = CGFloat((14 + norm * 40).rounded())
            let weight: Font.Weight = norm > 0.6 ? .bold : (norm > 0.3 ? .semibold : .medium)
            return Sized(text: word.text, size: size, weight: weight, color: palette[index % palette.count])
        }

        // 3) Archimedean-spiral placement with an occupancy grid.
        let cell: CGFloat = 4
        let cols = Int((canvas / cell).rounded(.up))
        let rows = cols
        var occupied = [Bool](repeating: false, count: cols * rows)
        let mid = canvas / 2
        let pad: CGFloat = 3
        var placed: [PlacedWord] = []

        for item in sized {
            let w = estimateWidth(item.text, size: item.size).rounded(.up) + pad * 2
            let h = (item.size * 1.18).rounded(.up) + pad * 2
            for step in 0..<5000 {
                let t = Double(step) * 0.22
                let r = 2.5 * t
                let x = (mid + CGFloat(r * cos(t)) - w / 2).rounded()
                let y = (mid + CGFloat(r * sin(t)) - h / 2).rounded()
                if x < 0 || y < 0 || x + w > canvas || y + h > canvas { continue }
                let c0 = Int(x / cell), r0 = Int(y / cell)
                let c1 = Int(((x + w) / cell).rounded(.up)), r1 = Int(((y + h) / cell).rounded(.up))
                var clash = false
                rowLoop: for ri in r0..<r1 where ri >= 0 && ri < rows {
                    for ci in c0..<c1 where ci >= 0 && ci < cols {
                        if occupied[ri * cols + ci] { clash = true; break rowLoop }
                    }
                }
                if clash { continue }
                for ri in r0..<r1 where ri >= 0 && ri < rows {
                    for ci in c0..<c1 where ci >= 0 && ci < cols {
                        occupied[ri * cols + ci] = true
                    }
                }
                placed.append(PlacedWord(text: item.text, size: item.size, weight: item.weight,
                                         color: item.color, center: CGPoint(x: x + w / 2, y: y + h / 2)))
                break
            }
        }
        return placed
    }

    private static func estimateWidth(_ text: String, size: CGFloat) -> CGFloat {
        var acc: CGFloat = 0
        for scalar in text.unicodeScalars { acc += scalar.value < 128 ? 0.58 : 1.0 }
        return acc * size
    }
}

private extension Color {
    init(hex: UInt) {
        self.init(
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255
        )
    }
}

/// 教学环节总结 — vertical timeline of structured teaching segments.
struct TeachTimelineView: View {
    let sections: [TeachSummarySection]
    var contentLineLimit: Int? = nil
    var highlight: String = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            ForEach(sections) { section in
                if !section.summary.isEmpty {
                    Text(ReportFormat.highlight(section.summary, query: highlight))
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                ForEach(Array(section.segments.enumerated()), id: \.element.id) { index, segment in
                    row(segment, isLast: index == section.segments.count - 1)
                }
            }
        }
    }

    private func row(_ segment: TeachSegment, isLast: Bool) -> some View {
        HStack(alignment: .top, spacing: 10) {
            VStack(spacing: 0) {
                Circle().fill(ReportPalette.primary).frame(width: 8, height: 8).padding(.top, 5)
                if !isLast {
                    Rectangle().fill(Color.gray.opacity(0.25)).frame(width: 1.5).frame(maxHeight: .infinity)
                }
            }
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(ReportFormat.highlight(segment.type, query: highlight))
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(ReportPalette.primary)
                    Spacer()
                    if !segment.startTime.isEmpty {
                        Text("\(segment.startTime) - \(segment.endTime)")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }
                if !segment.content.isEmpty {
                    Text(ReportFormat.highlight(segment.content, query: highlight))
                        .font(.footnote).lineLimit(contentLineLimit)
                }
                if !segment.keypoint.isEmpty {
                    HStack(alignment: .top, spacing: 2) {
                        Text("关键点：").font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
                        Text(ReportFormat.highlight(segment.keypoint, query: highlight))
                            .font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }
            .padding(.bottom, isLast ? 0 : 4)
        }
    }
}

enum ReportFormat {
    /// Formats seconds as "H:MM:SS" or "M:SS".
    static func clock(_ seconds: Double) -> String {
        let total = Int(seconds)
        let h = total / 3600
        let m = (total % 3600) / 60
        let s = total % 60
        return h > 0 ? String(format: "%d:%02d:%02d", h, m, s) : String(format: "%d:%02d", m, s)
    }

    /// Returns `text` with every case-insensitive occurrence of `query` highlighted.
    static func highlight(_ text: String, query: String) -> AttributedString {
        var attributed = AttributedString(text)
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return attributed }
        var searchStart = text.startIndex
        while searchStart < text.endIndex,
              let range = text.range(of: trimmed, options: .caseInsensitive, range: searchStart..<text.endIndex) {
            if let low = AttributedString.Index(range.lowerBound, within: attributed),
               let high = AttributedString.Index(range.upperBound, within: attributed) {
                attributed[low..<high].backgroundColor = Color.yellow.opacity(0.45)
                attributed[low..<high].foregroundColor = Color.primary
            }
            searchStart = range.upperBound
        }
        return attributed
    }
}

/// Full-screen 教学环节总结 pushed from the report, with on-page search.
struct TeachSummaryFullView: View {
    let sections: [TeachSummarySection]
    @State private var query = ""

    private var trimmedQuery: String { query.trimmingCharacters(in: .whitespacesAndNewlines) }

    private var filteredSections: [TeachSummarySection] {
        guard !trimmedQuery.isEmpty else { return sections }
        var result: [TeachSummarySection] = []
        for section in sections {
            let segments = section.segments.filter {
                $0.type.localizedCaseInsensitiveContains(trimmedQuery)
                    || $0.content.localizedCaseInsensitiveContains(trimmedQuery)
                    || $0.keypoint.localizedCaseInsensitiveContains(trimmedQuery)
            }
            let summaryHit = section.summary.localizedCaseInsensitiveContains(trimmedQuery)
            if !segments.isEmpty || summaryHit {
                result.append(TeachSummarySection(
                    summary: summaryHit ? section.summary : "",
                    segments: segments.isEmpty ? section.segments : segments
                ))
            }
        }
        return result
    }

    var body: some View {
        ScrollView {
            if filteredSections.isEmpty {
                Text("未找到匹配内容")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                TeachTimelineView(sections: filteredSections, highlight: trimmedQuery)
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .navigationTitle("教学环节总结")
        .navigationBarTitleDisplayMode(.inline)
        .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .always), prompt: "搜索教学环节")
    }
}

extension ReportPalette {
    /// Green / amber / red by score band (mirrors the web's score-high/mid/low).
    static func scoreColor(_ score: Int) -> Color {
        if score >= 80 { return Color(red: 0x40 / 255, green: 0xB5 / 255, blue: 0x5E / 255) }
        if score >= 60 { return Color(red: 0xE8 / 255, green: 0xB8 / 255, blue: 0x4D / 255) }
        return Color(red: 0xE3 / 255, green: 0x6B / 255, blue: 0x6B / 255)
    }

    /// Stable color for an interaction 题型 (记忆/理解/应用/分析/评价/创新).
    static func interactionTypeColor(_ type: String) -> Color {
        let order = ["记忆型", "理解型", "应用型", "分析型", "评价型", "创新型"]
        if let index = order.firstIndex(of: type) { return color(index) }
        return primary
    }
}

/// Small colored score capsule ("87分") used by the analysis cards.
struct ScorePill: View {
    let score: Int
    var body: some View {
        Text("\(score)分")
            .font(.caption.weight(.semibold))
            .foregroundStyle(ReportPalette.scoreColor(score))
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(ReportPalette.scoreColor(score).opacity(0.14), in: Capsule())
    }
}

/// Horizontal bar chart with a left category axis and a bottom value axis (rounded to a
/// "nice" max). Used for the 语言精炼度 filler-word counts.
struct HorizontalBarChart: View {
    let items: [(label: String, value: Int)]

    var body: some View {
        let rawMax = items.map { $0.value }.max() ?? 1
        let step = Self.niceStep(rawMax)
        let niceMax = max(step, Int((Double(rawMax) / Double(step)).rounded(.up)) * step)
        let ticks = Array(stride(from: 0, through: niceMax, by: step))

        Canvas { context, size in
            let labelWidth: CGFloat = 50
            let axisHeight: CGFloat = 20
            let plotLeft = labelWidth
            let plotRight = size.width - 6
            let plotWidth = max(1, plotRight - plotLeft)
            let plotTop: CGFloat = 4
            let plotBottom = size.height - axisHeight
            let rowHeight = max(1, plotBottom - plotTop) / CGFloat(max(1, items.count))
            let barHeight = min(rowHeight * 0.55, 22)

            func xFor(_ value: Double) -> CGFloat {
                plotLeft + plotWidth * CGFloat(value) / CGFloat(niceMax)
            }

            for tick in ticks {
                let gx = xFor(Double(tick))
                var line = Path()
                line.move(to: CGPoint(x: gx, y: plotTop))
                line.addLine(to: CGPoint(x: gx, y: plotBottom))
                context.stroke(line, with: .color(.gray.opacity(tick == 0 ? 0.35 : 0.16)), lineWidth: 1)
                context.draw(
                    Text("\(tick)").font(.caption2).foregroundColor(.secondary),
                    at: CGPoint(x: gx, y: plotBottom + 10), anchor: .center
                )
            }

            for (index, item) in items.enumerated() {
                let cy = plotTop + rowHeight * (CGFloat(index) + 0.5)
                context.draw(
                    Text(item.label).font(.footnote).foregroundColor(.primary),
                    at: CGPoint(x: plotLeft - 10, y: cy), anchor: .trailing
                )
                let width = plotWidth * CGFloat(item.value) / CGFloat(niceMax)
                let rect = CGRect(x: plotLeft, y: cy - barHeight / 2, width: max(0, width), height: barHeight)
                context.fill(Path(roundedRect: rect, cornerRadius: 2), with: .color(ReportPalette.primary))
            }
        }
        .frame(height: CGFloat(items.count) * 40 + 24)
    }

    /// Tick spacing chosen so the axis has roughly 5–6 labels.
    private static func niceStep(_ value: Int) -> Int {
        switch value {
        case ...10:     return 2
        case 11...30:   return 5
        case 31...60:   return 10
        case 61...150:  return 25
        default:        return 50
        }
    }
}

/// 语言精炼度 — top filler/crutch words with a count bar chart and example utterances.
struct FillerWordsView: View {
    let words: [FillerWord]
    var ratio: Double?
    var count: Int?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let meta = metaText {
                Text(meta).font(.caption2).foregroundStyle(.tertiary)
            }
            if !words.isEmpty {
                HorizontalBarChart(items: words.prefix(8).map { (label: $0.term, value: $0.count) })
            }
            ForEach(words.prefix(5)) { word in
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Text(word.term)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(ReportPalette.primary)
                        Text("×\(word.count)").font(.caption).foregroundStyle(.secondary)
                    }
                    ForEach(word.examples.prefix(2)) { example in
                        HStack(alignment: .top, spacing: 8) {
                            Text(ReportFormat.clock(example.time))
                                .font(.caption2.monospaced())
                                .foregroundStyle(.tertiary)
                                .frame(width: 44, alignment: .leading)
                            Text(ReportFormat.highlight(example.text, query: word.term))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(2)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private var metaText: String? {
        var parts: [String] = []
        if let ratio { parts.append("冗余填充词占比 \(String(format: "%.1f", ratio * 100))%") }
        if let count { parts.append("共 \(count) 次") }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
}

/// 导入/总结环节分析 — a graded phase with its description and evaluation.
struct PhaseAnalysisCard: View {
    let title: String
    let analysis: PhaseAnalysis

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text(title).font(.subheadline.weight(.semibold))
                if !analysis.timeRange.isEmpty {
                    Text(analysis.timeRange).font(.caption2).foregroundStyle(.tertiary)
                }
                Spacer()
                ScorePill(score: analysis.score)
            }
            if !analysis.description.isEmpty {
                Text(analysis.description).font(.footnote)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !analysis.evaluation.isEmpty {
                Text(analysis.evaluation).font(.caption).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.tertiarySystemBackground), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

/// 互动事件时间轴 — chronological interaction events with their cognitive type.
struct InteractionTimelineView: View {
    let events: [InteractionEvent]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(events) { event in
                HStack(alignment: .top, spacing: 10) {
                    Text(ReportFormat.clock(event.time))
                        .font(.caption2.monospaced())
                        .foregroundStyle(ReportPalette.primary)
                        .frame(width: 48, alignment: .leading)
                    VStack(alignment: .leading, spacing: 4) {
                        if !event.type.isEmpty {
                            Text(event.type)
                                .font(.caption2.weight(.medium))
                                .padding(.horizontal, 6).padding(.vertical, 2)
                                .background(ReportPalette.interactionTypeColor(event.type).opacity(0.15), in: Capsule())
                                .foregroundStyle(ReportPalette.interactionTypeColor(event.type))
                        }
                        Text(event.text).font(.footnote)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
    }
}

/// Full-screen 互动事件时间轴 pushed from the report (all events).
struct InteractionTimelineFullView: View {
    let events: [InteractionEvent]

    var body: some View {
        ScrollView {
            InteractionTimelineView(events: events)
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .navigationTitle("互动事件时间轴")
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// 思政事件 — one ideological-integration moment with its naturalness score and evaluation.
struct IdeologyEventCard: View {
    let event: IdeologyEvent

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text(event.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(ReportPalette.primary)
                Spacer()
                if !event.timeRange.isEmpty {
                    Text(event.timeRange).font(.caption2).foregroundStyle(.tertiary)
                }
                ScorePill(score: event.score)
            }
            if !event.content.isEmpty {
                Text(event.content).font(.footnote)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !event.evaluation.isEmpty {
                Text(event.evaluation).font(.caption).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.tertiarySystemBackground), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

/// 知识点分布 — nested knowledge tree rendered as an indented outline. `maxDepth` limits how
/// many levels render (nil = unlimited); the report preview uses 0 to show top-level topics only.
struct KnowledgeTreeView: View {
    let nodes: [KnowledgeNode]
    var maxDepth: Int? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(nodes) { node in
                KnowledgeNodeRow(node: node, depth: 0, maxDepth: maxDepth)
            }
        }
    }
}

private struct KnowledgeNodeRow: View {
    let node: KnowledgeNode
    let depth: Int
    var maxDepth: Int? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Circle()
                    .fill(depth == 0 ? ReportPalette.primary : Color.gray.opacity(0.4))
                    .frame(width: depth == 0 ? 7 : 5, height: depth == 0 ? 7 : 5)
                Text(node.title)
                    .font(depth == 0 ? .subheadline.weight(.semibold) : .footnote)
                    .foregroundStyle(depth == 0 ? Color.primary : Color.secondary)
                Spacer(minLength: 4)
                if !node.timeRange.isEmpty {
                    Text(node.timeRange).font(.caption2).foregroundStyle(.tertiary)
                }
            }
            if !node.children.isEmpty, maxDepth == nil || depth < maxDepth! {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(node.children) { child in
                        KnowledgeNodeRow(node: child, depth: depth + 1, maxDepth: maxDepth)
                    }
                }
                .padding(.leading, 14)
            }
        }
    }
}

/// Full-screen 知识点分布 pushed from the report (complete tree, all levels).
struct KnowledgeTreeFullView: View {
    let nodes: [KnowledgeNode]

    var body: some View {
        ScrollView {
            KnowledgeTreeView(nodes: nodes)
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .navigationTitle("知识点分布")
        .navigationBarTitleDisplayMode(.inline)
    }
}
