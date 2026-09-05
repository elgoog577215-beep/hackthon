import SwiftUI

/// 本地视频 prep step: confirm the file + name, then hand off to the list, which runs the actual
/// chunked upload (so it survives this sheet closing — progress then shows in the list banner,
/// mirroring the 智云 import flow). No analysis is started here; the uploaded video lands
/// 未开始分析 and the user picks 云端 / 本地 on its detail page.
struct CustomVideoUploadView: View {
    let fileURL: URL
    let onUpload: (URL, String) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var videoName: String

    init(fileURL: URL, onUpload: @escaping (URL, String) -> Void) {
        self.fileURL = fileURL
        self.onUpload = onUpload
        let suggested = fileURL.deletingPathExtension().lastPathComponent
        _videoName = State(initialValue: suggested.isEmpty ? "未命名视频" : suggested)
    }

    private var canStart: Bool {
        !videoName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        Form {
            Section("文件") {
                LabeledContent("文件名", value: fileURL.lastPathComponent)
                    .lineLimit(1)
            }

            Section("视频名称") {
                TextField("用于在列表中识别", text: $videoName)
            }

            Section {
                Button {
                    onUpload(fileURL, videoName)
                } label: {
                    Label("开始上传", systemImage: "arrow.up.circle.fill")
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .disabled(!canStart)
            }

            Section {
                Text("上传将在列表中显示进度，可随时返回；完成后在详情页选择分析方式（云端 / 本地）。")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .labelStyle(.tight)
        .navigationTitle("本地视频")
        .navigationBarTitleDisplayMode(.inline)
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Button("返回") { dismiss() }
            }
        }
    }
}
