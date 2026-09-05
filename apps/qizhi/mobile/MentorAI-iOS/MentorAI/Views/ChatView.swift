import SwiftUI
import MarkdownUI
import UniformTypeIdentifiers

struct ChatView: View {
    @StateObject private var viewModel: ChatViewModel
    @FocusState private var inputFocused: Bool
    @State private var fileImporterShown: Bool = false
    private let onClose: () -> Void

    init(viewModel: ChatViewModel, onClose: @escaping () -> Void = {}) {
        _viewModel = StateObject(wrappedValue: viewModel)
        self.onClose = onClose
    }

    var body: some View {
        VStack(spacing: 0) {
            if showWelcome {
                welcomeState
            } else {
                messageStack
            }
            statusOverlay
            attachmentTray
            Divider()
            inputBar
        }
        .navigationTitle(viewModel.titleForDisplay)
        .navigationBarTitleDisplayMode(.inline)
        // Hide the parent TabView's bottom bar while the chat detail is on screen; SwiftUI
        // restores it automatically when this view is popped back to SessionListView.
        .toolbar(.hidden, for: .tabBar)
        .task {
            await viewModel.load()
        }
        .onDisappear { onClose() }
        .fileImporter(
            isPresented: $fileImporterShown,
            allowedContentTypes: ChatView.allowedUploadTypes,
            allowsMultipleSelection: true
        ) { result in
            switch result {
            case .success(let urls):
                for url in urls { viewModel.addAttachment(localURL: url) }
            case .failure(let error):
                viewModel.streamError = error.localizedDescription
            }
        }
    }

    private static let allowedUploadTypes: [UTType] = {
        let candidates: [UTType?] = [
            .pdf, .plainText, .text, .image, .movie, .audio,
            UTType(filenameExtension: "md"),
            UTType(filenameExtension: "doc"),
            UTType(filenameExtension: "docx"),
            UTType(filenameExtension: "ppt"),
            UTType(filenameExtension: "pptx"),
            UTType(filenameExtension: "xls"),
            UTType(filenameExtension: "xlsx"),
            .data,
        ]
        return candidates.compactMap { $0 }
    }()

    private var messageStack: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(spacing: 16) {
                    if viewModel.isLoadingSession {
                        ProgressView().padding(.vertical, 32)
                    }
                    if let err = viewModel.sessionError {
                        InlineError(text: err) {
                            Task { await viewModel.load() }
                        }
                    }
                    ForEach(Array(viewModel.messages.enumerated()), id: \.offset) { offset, msg in
                        MessageBubble(message: msg, isStreamingTail: isStreamingTail(at: offset))
                            .id(offset)
                    }
                    if let err = viewModel.streamError {
                        InlineError(text: err, retry: nil)
                    }
                    Color.clear.frame(height: 1).id("BOTTOM")
                }
                .padding(.horizontal, 16)
                .padding(.top, 12)
                .padding(.bottom, 12)
                .background(
                    GeometryReader { geo in
                        Color.clear.preference(key: ContentHeightKey.self, value: geo.size.height)
                    }
                )
            }
            // Drag the scroll view down to dismiss the keyboard interactively (iOS Messages-style).
            .scrollDismissesKeyboard(.interactively)
            // Tap any empty area of the scroll view to dismiss the keyboard. `simultaneousGesture`
            // runs alongside scroll + text-selection, so neither is broken.
            .simultaneousGesture(
                TapGesture().onEnded { inputFocused = false }
            )
            .onChange(of: viewModel.messages.count) { _ in
                scrollToBottom(proxy)
            }
            .onChange(of: viewModel.messages.last?.content) { _ in
                scrollToBottom(proxy)
            }
            .onChange(of: viewModel.statusText) { _ in
                scrollToBottom(proxy)
            }
            // When the user focuses the input the keyboard slides up and shrinks the visible
            // area; re-pin to the bottom so the latest message stays in view. The delayed
            // second pass catches the moment after the keyboard animation finishes.
            .onChange(of: inputFocused) { focused in
                guard focused else { return }
                scrollToBottom(proxy)
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                    scrollToBottom(proxy)
                }
            }
            // A plain VStack measures every row up front (LazyVStack only estimates
            // off-screen rows, so scrollTo under-shoots on first load), but Markdown
            // still finalizes its height asynchronously. Re-pin to the bottom whenever
            // the measured content height changes so the detail page opens already
            // scrolled to the newest message.
            .onPreferenceChange(ContentHeightKey.self) { _ in
                guard !viewModel.messages.isEmpty else { return }
                scrollToBottom(proxy)
            }
        }
    }

    private var showWelcome: Bool {
        viewModel.messages.isEmpty && !viewModel.isLoadingSession && viewModel.sessionError == nil
    }

    private static let suggestions = [
        "帮我设计一节课的教学大纲",
        "围绕一个知识点出 5 道练习题",
        "把一段课文改写得更通俗易懂",
        "总结一份资料的核心要点"
    ]

    private var welcomeState: some View {
        ScrollView {
            VStack(spacing: 28) {
                VStack(spacing: 14) {
                    Image(systemName: "sparkles")
                        .font(.system(size: 30, weight: .semibold))
                        .foregroundStyle(.white)
                        .frame(width: 64, height: 64)
                        .background(Color.accentColor.gradient, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    Text("你好，我是启智")
                        .font(.title2.weight(.semibold))
                    Text("可以帮你备课、出题、分析资料，试试下面的问题")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }

                VStack(spacing: 10) {
                    ForEach(Self.suggestions, id: \.self) { suggestion in
                        Button {
                            useSuggestion(suggestion)
                        } label: {
                            HStack(spacing: 10) {
                                Image(systemName: "lightbulb")
                                    .foregroundStyle(Color.accentColor)
                                Text(suggestion)
                                    .foregroundStyle(.primary)
                                    .multilineTextAlignment(.leading)
                                Spacer(minLength: 8)
                                Image(systemName: "arrow.up")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(.tertiary)
                            }
                            .padding(.horizontal, 14)
                            .padding(.vertical, 12)
                            .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 24)
            .padding(.top, 56)
            .padding(.bottom, 24)
        }
        // Match the message-stack behaviour: drag dismisses, tap on empty area dismisses.
        .scrollDismissesKeyboard(.interactively)
        .simultaneousGesture(
            TapGesture().onEnded { inputFocused = false }
        )
    }

    private func useSuggestion(_ text: String) {
        Haptics.tap()
        viewModel.draft = text
        viewModel.send()
        inputFocused = false
    }

    private func isStreamingTail(at index: Int) -> Bool {
        viewModel.isStreaming &&
            index == viewModel.messages.count - 1 &&
            viewModel.messages[index].role == .assistant
    }

    private func scrollToBottom(_ proxy: ScrollViewProxy) {
        // Animate only while a live reply streams in; opening a conversation should
        // jump straight to the bottom without a visible top-to-bottom scroll.
        if viewModel.isStreaming {
            withAnimation(.easeOut(duration: 0.15)) {
                proxy.scrollTo("BOTTOM", anchor: .bottom)
            }
        } else {
            proxy.scrollTo("BOTTOM", anchor: .bottom)
        }
    }

    @ViewBuilder
    private var statusOverlay: some View {
        if viewModel.isStreaming, let status = viewModel.statusText, !status.isEmpty {
            HStack(spacing: 8) {
                ProgressView().scaleEffect(0.7)
                Text(status)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 6)
            .background(Color(.secondarySystemBackground))
            .transition(.opacity.combined(with: .move(edge: .bottom)))
        }
    }

    @ViewBuilder
    private var attachmentTray: some View {
        if !viewModel.attachments.isEmpty {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(viewModel.attachments) { attachment in
                        AttachmentChip(attachment: attachment) {
                            viewModel.removeAttachment(id: attachment.id)
                        }
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
            }
            .background(Color(.secondarySystemBackground))
        }
    }

    private var inputBar: some View {
        HStack(alignment: .center, spacing: 8) {
            Button {
                fileImporterShown = true
            } label: {
                Image(systemName: "paperclip.circle.fill")
                    .font(.system(size: 30))
                    .foregroundStyle(viewModel.isStreaming ? Color.secondary : Color.accentColor)
            }
            .disabled(viewModel.isStreaming)
            .accessibilityLabel("添加附件")

            TextField("发送消息", text: $viewModel.draft, axis: .vertical)
                .focused($inputFocused)
                .lineLimit(1...5)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                .disabled(viewModel.isStreaming)

            if viewModel.isStreaming {
                Button {
                    viewModel.cancel()
                } label: {
                    Image(systemName: "stop.circle.fill")
                        .font(.system(size: 30))
                        .foregroundStyle(.red)
                }
                .accessibilityLabel("停止")
            } else {
                Button {
                    Haptics.tap()
                    viewModel.send()
                    inputFocused = false
                } label: {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.system(size: 30))
                        .foregroundStyle(viewModel.canSend ? Color.accentColor : Color.secondary)
                }
                .disabled(!viewModel.canSend)
                .accessibilityLabel("发送")
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color(.systemBackground))
    }
}

private struct MessageBubble: View {
    let message: ChatMessage
    let isStreamingTail: Bool

    private var isTyping: Bool {
        message.content.isEmpty && isStreamingTail
    }

    var body: some View {
        if message.role == .user {
            HStack(alignment: .top, spacing: 10) {
                Spacer(minLength: 48)
                userBubble
            }
        } else if isTyping {
            // Centre the typing dots on the avatar's centerline; long replies stay top-aligned.
            HStack(alignment: .center, spacing: 10) {
                avatar
                TypingIndicator()
                Spacer(minLength: 0)
            }
        } else {
            HStack(alignment: .top, spacing: 10) {
                avatar
                assistantContent
                Spacer(minLength: 0)
            }
        }
    }

    private var avatar: some View {
        Image(systemName: "sparkles")
            .font(.system(size: 13, weight: .bold))
            .foregroundStyle(.white)
            .frame(width: 28, height: 28)
            .background(Color.accentColor.gradient, in: Circle())
    }

    // User turns keep an accent bubble; assistant turns render borderless and
    // full-width (Claude-style) for cleaner, more readable long-form replies.
    private var userBubble: some View {
        content
            .padding(.horizontal, 14)
            .padding(.vertical, 9)
            .foregroundStyle(.white)
            .background(Color.accentColor, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .textSelection(.enabled)
    }

    private var assistantContent: some View {
        content
            .foregroundStyle(.primary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, 3)
            .textSelection(.enabled)
    }

    @ViewBuilder
    private var content: some View {
        if message.content.isEmpty && isStreamingTail {
            TypingIndicator()
        } else if message.content.isEmpty {
            Text("…")
                .foregroundStyle(.secondary)
        } else if message.role == .user {
            Text(message.content)
                .fixedSize(horizontal: false, vertical: true)
        } else {
            // While streaming, the backend sends content with literal escapes (\n, \" …);
            // decode for display. Finished/loaded messages are already decoded. Then relax
            // CJK + punctuation flanking so `**X(青教赛)**的备赛` renders bold instead of
            // emitting literal `**` — CommonMark's strict flanking rules otherwise reject
            // the closing delimiter for the very common "punct adjacent to CJK" pattern.
            let raw = isStreamingTail ? message.content.decodingJSONEscapes() : message.content
            Markdown(raw.relaxingCJKBoldFlanking())
                .markdownTheme(.chatAssistant)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

private struct TypingIndicator: View {
    @State private var phase: Int = 0

    var body: some View {
        HStack(spacing: 4) {
            ForEach(0..<3) { i in
                Circle()
                    .frame(width: 6, height: 6)
                    .foregroundStyle(phase == i ? Color.primary : Color.secondary)
            }
        }
        .onAppear {
            Timer.scheduledTimer(withTimeInterval: 0.35, repeats: true) { _ in
                phase = (phase + 1) % 3
            }
        }
        .frame(minWidth: 30)
    }
}

private struct AttachmentChip: View {
    let attachment: ChatAttachment
    let onRemove: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: iconName)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(tint)
                .frame(width: 24, height: 24)
                .background(tint.opacity(0.15), in: RoundedRectangle(cornerRadius: 6, style: .continuous))

            VStack(alignment: .leading, spacing: 2) {
                Text(attachment.filename)
                    .font(.footnote)
                    .lineLimit(1)
                    .truncationMode(.middle)
                statusLabel
            }
            .frame(maxWidth: 180, alignment: .leading)

            Button(action: onRemove) {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 16))
                    .foregroundStyle(.tertiary)
            }
            .accessibilityLabel("移除")
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(Color(.systemBackground), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(borderColor, lineWidth: 1)
        )
    }

    @ViewBuilder
    private var statusLabel: some View {
        switch attachment.status {
        case .uploading:
            HStack(spacing: 4) {
                ProgressView().scaleEffect(0.6).frame(width: 10, height: 10)
                Text("上传中…")
            }
            .font(.caption2)
            .foregroundStyle(.secondary)
        case .done:
            Text(attachment.displaySize)
                .font(.caption2)
                .foregroundStyle(.secondary)
        case .error(let message):
            Text(message)
                .font(.caption2)
                .foregroundStyle(.red)
                .lineLimit(1)
        }
    }

    private var iconName: String {
        switch attachment.fileExtension {
        case "pdf": return "doc.richtext"
        case "doc", "docx": return "doc.text"
        case "ppt", "pptx": return "rectangle.on.rectangle"
        case "xls", "xlsx": return "tablecells"
        case "txt", "md": return "text.alignleft"
        case "jpg", "jpeg", "png", "gif", "webp", "bmp", "svg": return "photo"
        case "mp4", "mov", "webm", "mkv", "avi", "m4v": return "film"
        default: return "doc"
        }
    }

    private var tint: Color {
        switch attachment.status {
        case .uploading: return .secondary
        case .done: return .accentColor
        case .error: return .red
        }
    }

    private var borderColor: Color {
        switch attachment.status {
        case .error: return .red.opacity(0.4)
        default: return .gray.opacity(0.25)
        }
    }
}

private struct ContentHeightKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}

private struct InlineError: View {
    let text: String
    var retry: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(text, systemImage: "exclamationmark.triangle.fill")
                .foregroundStyle(.red)
                .font(.footnote)
            if let retry {
                Button("重试", action: retry)
                    .font(.footnote)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(Color.red.opacity(0.1), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}
