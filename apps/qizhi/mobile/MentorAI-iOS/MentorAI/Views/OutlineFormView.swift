import SwiftUI

struct OutlineFormView: View {
    let api: ResourceAPI
    let tokenProvider: () -> String?
    let onSaved: (ResourceSummary) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var form = OutlineForm()
    @State private var path: [Route] = []
    @State private var generatorVM: ResourceGeneratorViewModel?

    private enum Route: Hashable { case generator }

    private let courseNatureOptions = ["专业必修课", "专业选修课", "通识必修课", "通识选修课", "实践课", "其它"]
    private let teachingMethodOptions = ["线下", "线上", "线上线下混合"]
    private let gradeOptions = ["大学一年级", "大学二年级", "大学三年级", "大学四年级", "研究生一年级", "研究生二年级"]

    var body: some View {
        NavigationStack(path: $path) {
            Form {
                Section("课程信息") {
                    TextField("课程名称", text: $form.courseName)
                    Picker("课程性质", selection: $form.courseNature) {
                        ForEach(courseNatureOptions, id: \.self) { Text($0).tag($0) }
                    }
                    TextField("课程类别（如计算机类、人文类）", text: $form.courseCategory)
                    HStack {
                        Stepper(value: $form.credits, in: 1...20) {
                            Text("学分：\(form.credits)")
                        }
                    }
                    HStack {
                        Stepper(value: $form.hours, in: 8...256, step: 4) {
                            Text("学时：\(form.hours)")
                        }
                    }
                }

                Section("授课对象") {
                    TextField("授课专业（如软件工程）", text: $form.targetMajor)
                    Picker("授课年级", selection: $form.targetGrade) {
                        ForEach(gradeOptions, id: \.self) { Text($0).tag($0) }
                    }
                }

                Section("授课方式") {
                    Picker("授课方式", selection: $form.teachingMethod) {
                        ForEach(teachingMethodOptions, id: \.self) { Text($0).tag($0) }
                    }
                    VStack(alignment: .leading) {
                        Text("线下学时占比：\(form.offlineHoursRatio)%")
                        Slider(value: bindingInt($form.offlineHoursRatio), in: 0...100, step: 5)
                    }
                    VStack(alignment: .leading) {
                        Text("线下成绩占比：\(form.offlineScoreRatio)%")
                        Slider(value: bindingInt($form.offlineScoreRatio), in: 0...100, step: 5)
                    }
                }

                Section("课程内容") {
                    TextField("预修要求（可选填若干门课程）", text: $form.prerequisites, axis: .vertical)
                        .lineLimit(2...4)
                    TextField("课程介绍", text: $form.courseIntroduction, axis: .vertical)
                        .lineLimit(3...8)
                    TextField("教学目标", text: $form.teachingObjectives, axis: .vertical)
                        .lineLimit(3...8)
                    TextField("思政内容（可选）",
                              text: Binding(
                                get: { form.ideologicalPolitical ?? "" },
                                set: { form.ideologicalPolitical = $0.isEmpty ? nil : $0 }
                              ),
                              axis: .vertical)
                        .lineLimit(2...6)
                }

                Section {
                    Button {
                        startGeneration()
                    } label: {
                        Label("开始生成", systemImage: "sparkles")
                            .foregroundStyle(.white)
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!form.isValid)
                } footer: {
                    if !form.isValid {
                        Text("请至少填写课程名称、类别、授课专业、课程介绍、教学目标。")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("新建教学大纲")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("取消") { dismiss() }
                }
            }
            .navigationDestination(for: Route.self) { _ in
                if let vm = generatorVM {
                    ResourceGeneratorView(viewModel: vm) { savedSummary in
                        onSaved(savedSummary)
                        dismiss()
                    }
                } else {
                    EmptyView()
                }
            }
        }
    }

    private func startGeneration() {
        let req = ResourceGenerateRequest(
            operation: .create,
            resourceType: .outline,
            outlineForm: form
        )
        generatorVM = ResourceGeneratorViewModel(
            request: req,
            defaultName: form.courseName.isEmpty ? "新建教学大纲" : "\(form.courseName) · 教学大纲",
            api: api,
            tokenProvider: tokenProvider
        )
        path.append(.generator)
    }

    private func bindingInt(_ source: Binding<Int>) -> Binding<Double> {
        Binding<Double>(
            get: { Double(source.wrappedValue) },
            set: { source.wrappedValue = Int($0.rounded()) }
        )
    }
}
