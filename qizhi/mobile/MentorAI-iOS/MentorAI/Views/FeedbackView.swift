import SwiftUI
import UniformTypeIdentifiers

/// Mirrors `client/website/src/components/feedback/FeedbackModal.vue`. Presented as a sheet
/// from the Profile (我的) tab. Five-star rating + content textarea + optional attachments
/// (max 5, uploaded via the same `/attachment/upload` endpoint chat uses), then submits to
/// `POST /feedback`. Shows inline errors per field and a success/failure footer message.
struct FeedbackView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel: FeedbackViewModel
    @FocusState private var contentFocused: Bool
    @State private var fileImporterShown: Bool = false
    @State private var dismissWorkItem: DispatchWorkItem?

    init(viewModel: FeedbackViewModel) {
        _viewModel = StateObject(wrappedValue: viewModel)
    }

    var body: some View {
        NavigationStack {
            Form {
                ratingSection
                contentSection
                attachmentSection
                submitSection
            }
            .navigationTitle("用户评价与反馈")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { closeToolbar }
            .interactiveDismissDisabled(viewModel.isSubmitting)
            .fileImporter(
                isPresented: $fileImporterShown,
                allowedContentTypes: Self.allowedUploadTypes,
                allowsMultipleSelection: true
            ) { result in
                switch result {
                case .success(let urls):
                    for url in urls { viewModel.addAttachment(localURL: url) }
                case .failure(let error):
                    viewModel.submitMessage = error.localizedDescription
                    viewModel.submitIsError = true
                }
            }
            .onChange(of: viewModel.didSucceed) { success in
                guard success else { return }
                // Match the web modal's "auto-close after a brief success flash".
                dismissWorkItem?.cancel()
                let work = DispatchWorkItem { dismiss() }
                dismissWorkItem = work
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.8, execute: work)
            }
            .onDisappear { dismissWorkItem?.cancel() }
        }
    }

    // MARK: - Toolbar

    /// Typed `some ToolbarContent` so SwiftUI's `.toolbar(content:)` resolves unambiguously —
    /// passing an inline closure that contains a single `ToolbarItem` with a `.disabled` Button
    /// hits an overload-ambiguity in iOS 16's SwiftUI.
    @ToolbarContentBuilder
    private var closeToolbar: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            Button("关闭") { dismiss() }
                .disabled(viewModel.isSubmitting)
        }
    }

    // MARK: - Sections

    private var ratingSection: some View {
        Section("评分") {
            HStack(spacing: 4) {
                ForEach(1...5, id: \.self) { n in
                    Button {
                        Haptics.tap(.light)
                        viewModel.star = n
                    } label: {
                        Image(systemName: n <= viewModel.star ? "star.fill" : "star")
                            .font(.system(size: 32))
                            .foregroundStyle(n <= viewModel.star
                                             ? Color.accentColor
                                             : Color.gray.opacity(0.45))
                            .frame(maxWidth: .infinity)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("\(n) 星")
                    .accessibilityAddTraits(viewModel.star == n ? [.isSelected] : [])
                }
            }
            .padding(.vertical, 4)
            if let starError = viewModel.starError {
                Text(starError)
                    .font(.footnote)
                    .foregroundStyle(.red)
            }
        }
    }

    private var contentSection: some View {
        Section("反馈与建议") {
            TextEditor(text: $viewModel.content)
                .focused($contentFocused)
                .frame(minHeight: 140)
                .scrollContentBackground(.hidden)
                .overlay(alignment: .topLeading) {
                    if viewModel.content.isEmpty {
                        Text("在此输入您宝贵的反馈与建议……")
                            .foregroundStyle(.tertiary)
                            .padding(.top, 8)
                            .padding(.leading, 4)
                            .allowsHitTesting(false)
                    }
                }
            if let contentError = viewModel.contentError {
                Text(contentError)
                    .font(.footnote)
                    .foregroundStyle(.red)
            }
        }
    }

    private var attachmentSection: some View {
        Section {
            HStack {
                Text("最多 \(FeedbackMaxAttachments) 个")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                Spacer()
                Text("\(viewModel.attachments.count) / \(FeedbackMaxAttachments)")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
            }
            Button {
                fileImporterShown = true
            } label: {
                Label("选择附件", systemImage: "paperclip")
                    .frame(maxWidth: .infinity, alignment: .center)
            }
            .buttonStyle(.bordered)
            .disabled(viewModel.isSubmitting
                      || viewModel.attachments.count >= FeedbackMaxAttachments)

            if !viewModel.attachments.isEmpty {
                ForEach(viewModel.attachments) { attachment in
                    AttachmentRow(attachment: attachment) {
                        viewModel.removeAttachment(id: attachment.id)
                    }
                }
            }
            if let attachmentError = viewModel.attachmentError {
                Text(attachmentError)
                    .font(.footnote)
                    .foregroundStyle(.red)
            }
        } header: {
            Text("附件（可选）")
        }
    }

    private var submitSection: some View {
        Section {
            Button {
                Haptics.tap()
                contentFocused = false
                Task { await viewModel.submit() }
            } label: {
                HStack {
                    if viewModel.isSubmitting {
                        ProgressView().controlSize(.small)
                    }
                    Text(viewModel.isSubmitting ? "提交中…" : "确认并提交")
                        .font(.headline)
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(!viewModel.canSubmit)

            if let message = viewModel.submitMessage {
                Label(message, systemImage: viewModel.submitIsError
                      ? "exclamationmark.triangle.fill"
                      : "checkmark.circle.fill")
                    .font(.footnote)
                    .foregroundStyle(viewModel.submitIsError ? .red : .green)
            }
        }
    }

    /// Allowed file types — same set the chat attachment picker uses, so a single backend
    /// upload endpoint covers both flows.
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
}

// MARK: - Attachment row

private struct AttachmentRow: View {
    let attachment: FeedbackAttachment
    let onRemove: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: iconName)
                .font(.system(size: 16, weight: .medium))
                .foregroundStyle(tint)
                .frame(width: 32, height: 32)
                .background(tint.opacity(0.15), in: RoundedRectangle(cornerRadius: 8, style: .continuous))

            VStack(alignment: .leading, spacing: 2) {
                Text(attachment.filename)
                    .font(.footnote)
                    .lineLimit(1)
                    .truncationMode(.middle)
                statusLabel
            }

            Spacer(minLength: 0)

            Button {
                onRemove()
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 18))
                    .foregroundStyle(.tertiary)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("移除附件")
        }
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
        case "mp3", "wav", "m4a", "aac", "flac": return "waveform"
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
}
