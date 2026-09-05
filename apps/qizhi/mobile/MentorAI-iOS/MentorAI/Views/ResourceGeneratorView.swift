import SwiftUI
import MarkdownUI

struct ResourceGeneratorView: View {
    @ObservedObject var viewModel: ResourceGeneratorViewModel
    let onSaved: (ResourceSummary) -> Void

    var body: some View {
        VStack(spacing: 0) {
            statusBar
            Divider()
            preview
            Divider()
            actionBar
        }
        .navigationTitle("生成预览")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            if case .idle = viewModel.phase { viewModel.start() }
        }
    }

    @ViewBuilder
    private var statusBar: some View {
        HStack(spacing: 10) {
            switch viewModel.phase {
            case .idle:
                Image(systemName: "sparkles")
                Text("等待开始…")
            case .streaming:
                ProgressView().scaleEffect(0.7)
                Text(viewModel.statusText ?? "正在生成…")
                Spacer()
                Text("\(viewModel.wordCount) 字")
                    .foregroundStyle(.secondary)
            case .finished:
                Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                Text("生成完成")
                Spacer()
                Text("\(viewModel.wordCount) 字")
                    .foregroundStyle(.secondary)
            case .failed(let msg):
                Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.red)
                Text(msg).lineLimit(1)
            }
        }
        .font(.footnote)
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(Color(.secondarySystemBackground))
    }

    private var preview: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading) {
                    if viewModel.content.isEmpty {
                        Text("内容将在这里逐步出现…")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                            .padding(.top, 60)
                            .frame(maxWidth: .infinity, alignment: .center)
                    } else {
                        Markdown(viewModel.content)
                            .markdownTheme(.chatAssistant)
                            .textSelection(.enabled)
                    }
                    Color.clear.frame(height: 1).id("BOTTOM")
                }
                .padding(16)
            }
            .onChange(of: viewModel.content) { _ in
                withAnimation(.easeOut(duration: 0.12)) {
                    proxy.scrollTo("BOTTOM", anchor: .bottom)
                }
            }
        }
    }

    @ViewBuilder
    private var actionBar: some View {
        VStack(spacing: 8) {
            switch viewModel.phase {
            case .streaming:
                Button(role: .destructive) {
                    viewModel.cancel()
                } label: {
                    Label("停止", systemImage: "stop.circle.fill")
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
            case .finished:
                if viewModel.savedResourceID == nil {
                    TextField("资源名称", text: $viewModel.resourceName)
                        .textFieldStyle(.roundedBorder)
                    if let err = viewModel.saveError {
                        Text(err).font(.footnote).foregroundStyle(.red)
                    }
                    HStack(spacing: 12) {
                        Button(role: .destructive) {
                            viewModel.retry()
                        } label: {
                            Label("重新生成", systemImage: "arrow.clockwise")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        Button {
                            Task { await saveAndDismiss() }
                        } label: {
                            Label("保存", systemImage: "tray.and.arrow.down.fill")
                                .foregroundStyle(.white)
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(!viewModel.canSave)
                    }
                } else {
                    Label("已保存", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                        .frame(maxWidth: .infinity)
                }
            case .failed:
                Button {
                    viewModel.retry()
                } label: {
                    Label("重试", systemImage: "arrow.clockwise")
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
            case .idle:
                EmptyView()
            }
        }
        .padding(16)
    }

    private func saveAndDismiss() async {
        await viewModel.save()
        guard let newID = viewModel.savedResourceID else { return }
        let now = ISO8601DateFormatter().string(from: Date())
        let payload: [String: Any] = [
            "id": newID,
            "name": viewModel.resourceName,
            "resource_type": viewModel.resourceType.rawValue,
            "word_count": viewModel.wordCount,
            "create_time": now,
            "update_time": now,
        ]
        if let data = try? JSONSerialization.data(withJSONObject: payload),
           let summary = try? JSONDecoder().decode(ResourceSummary.self, from: data) {
            onSaved(summary)
        }
    }
}
