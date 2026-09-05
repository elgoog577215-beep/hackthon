import SwiftUI
import UniformTypeIdentifiers

struct NewVideoAnalysisView: View {
    let api: VideoAPI
    let tokenProvider: () -> String?
    /// Both flows hand off to the list (which runs them so they survive this sheet closing).
    let onZhiyunImport: (ZhiyunCourse) -> Void
    let onUpload: (URL, String) -> Void

    @EnvironmentObject private var appState: AppState
    @Environment(\.dismiss) private var dismiss
    @State private var path: [Route] = []
    @State private var fileImporterShown: Bool = false

    private enum Route: Hashable {
        case zhiyun
        case customUpload(url: URL)
    }

    var body: some View {
        NavigationStack(path: $path) {
            List {
                Section("选择来源") {
                    Button {
                        path.append(.zhiyun)
                    } label: {
                        SourceRow(
                            title: "智云课堂",
                            subtitle: appState.isTestMode
                                ? "需要浙大通行证登录后才可使用"
                                : "按时间筛选课程，导入后在详情页选择分析方式",
                            systemImage: "graduationcap.circle.fill",
                            tint: appState.isTestMode ? .gray : .blue
                        )
                    }
                    .buttonStyle(.plain)
                    .disabled(appState.isTestMode)

                    Button {
                        fileImporterShown = true
                    } label: {
                        SourceRow(
                            title: "本地视频",
                            subtitle: "从「文件」中选择视频，上传后在详情页选择分析方式",
                            systemImage: "square.and.arrow.up.circle.fill",
                            tint: .blue
                        )
                    }
                    .buttonStyle(.plain)
                }

                Section {
                    Text("分片上传按 5 MB 一片串行发送，过程中请保持页面前台。")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("新建视频分析")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("取消") { dismiss() }
                }
            }
            .fileImporter(
                isPresented: $fileImporterShown,
                allowedContentTypes: [.movie, .video, .quickTimeMovie, .mpeg4Movie],
                allowsMultipleSelection: false
            ) { result in
                switch result {
                case .success(let urls):
                    if let url = urls.first {
                        path.append(.customUpload(url: url))
                    }
                case .failure:
                    break
                }
            }
            .navigationDestination(for: Route.self) { route in
                switch route {
                case .zhiyun:
                    ZhiyunImportView(
                        api: api,
                        tokenProvider: tokenProvider,
                        onImport: { course in
                            onZhiyunImport(course)
                        }
                    )
                case .customUpload(let url):
                    CustomVideoUploadView(
                        fileURL: url,
                        onUpload: { fileURL, name in
                            onUpload(fileURL, name)
                        }
                    )
                }
            }
        }
    }
}

private struct SourceRow: View {
    let title: String
    let subtitle: String
    let systemImage: String
    let tint: Color

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: systemImage)
                .font(.system(size: 30))
                .foregroundStyle(tint)
                .frame(width: 32, height: 32)
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(.body)
                Text(subtitle).font(.footnote).foregroundStyle(.secondary)
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(.system(size: 12))
                .foregroundStyle(.tertiary)
        }
        .contentShape(Rectangle())
        .padding(.vertical, 4)
    }
}
