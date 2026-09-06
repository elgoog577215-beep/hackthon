# 知识维护面板真机验收结果

- 课程：`6808b11a-74ac-4df9-8e97-c02b4e1030e5`
- 前端：http://127.0.0.1:5611（真实 Chromium，非 jsdom）
- 场景：zh-desktop / en-desktop / zh-mobile-iphone15 / zh-mobile-iphonese

| 场景 | 步骤 | 结果 | 细节 |
| --- | --- | --- | --- |
| zh-desktop | 首页加载 | ✓ | http://127.0.0.1:5611/courses |
| zh-desktop | 进入课程 | ✓ | http://127.0.0.1:5611/course/6808b11a-74ac-4df9-8e97-c02b4e1030e5/learn |
| zh-desktop | 打开知识库浮层 | ✓ |  |
| zh-desktop | 知识库加载完成（非固定等待） | ✓ |  |
| zh-desktop | 知识树渲染出节点 | ✓ | 67 行 |
| zh-desktop | D2 横幅按数据显示（本课有依据→不该出现） | ✓ | count=0 |
| zh-desktop | 存在原子知识点 | ✓ |  |
| zh-desktop | 知识点详情有内容 | ✓ | 3331 字 |
| zh-desktop | D1 来源标签已本地化（无裸值泄漏） | ✓ | 资料来源 |
| zh-desktop | 知识维护面板存在 | ✓ |  |
| zh-desktop | AI 拆分候选返回结论 | ✓ | 该知识点是一个单一的定义，虽然包含适用条件和边界，但都是围绕同一个核心命题展开的，不涉及多个独立命题。 |
| zh-desktop | 影响面预览返回 | ✓ |  |
| zh-desktop | 影响面明细可读（非裸 ID） | ✓ | 需重建 21 待复核 115 被阻断 0 |
| zh-desktop | 确认后回执可见（不被刷新卸载） | ✓ | receipt=true panel=true |
| zh-desktop | 重建入口可点击并有反馈 | ✓ |  |
| zh-desktop | 修订历史列出本次改动 | ✓ | 2 条 · 修订知识陈述 learner_accept_zh 真机验收：验证改写→影响面→确认全链 修订知识陈述 |
| zh-desktop | 关系图渲染 | ✓ | 容器 3 |
| zh-desktop | 零 JS 异常 | ✓ |  |
| zh-desktop | 无非预期 4xx/5xx | ✓ |  |
| en-desktop | 首页加载 | ✓ | http://127.0.0.1:5611/courses |
| en-desktop | 进入课程 | ✓ | http://127.0.0.1:5611/course/6808b11a-74ac-4df9-8e97-c02b4e1030e5/learn |
| en-desktop | 打开知识库浮层 | ✓ |  |
| en-desktop | 知识库加载完成（非固定等待） | ✓ |  |
| en-desktop | 知识树渲染出节点 | ✓ | 67 行 |
| en-desktop | D2 横幅按数据显示（本课有依据→不该出现） | ✓ | count=0 |
| en-desktop | 存在原子知识点 | ✓ |  |
| en-desktop | 知识点详情有内容 | ✓ | 3934 字 |
| en-desktop | D1 来源标签已本地化（无裸值泄漏） | ✓ | Course materials |
| en-desktop | 关系图渲染 | ✓ | 容器 3 |
| en-desktop | 英文模式界面骨架无中文残留 | ✓ |  |
| en-desktop | 零 JS 异常 | ✓ |  |
| en-desktop | 无非预期 4xx/5xx | ✓ |  |
| zh-mobile-iphone15 | 首页加载 | ✓ | http://127.0.0.1:5611/courses |
| zh-mobile-iphone15 | 进入课程 | ✓ | http://127.0.0.1:5611/course/6808b11a-74ac-4df9-8e97-c02b4e1030e5/learn |
| zh-mobile-iphone15 | 打开知识库浮层 | ✓ |  |
| zh-mobile-iphone15 | 知识库加载完成（非固定等待） | ✓ |  |
| zh-mobile-iphone15 | 知识树渲染出节点 | ✓ | 67 行 |
| zh-mobile-iphone15 | D2 横幅按数据显示（本课有依据→不该出现） | ✓ | count=0 |
| zh-mobile-iphone15 | 存在原子知识点 | ✓ |  |
| zh-mobile-iphone15 | 知识点详情有内容 | ✓ | 3338 字 |
| zh-mobile-iphone15 | D1 来源标签已本地化（无裸值泄漏） | ✓ | 资料来源 |
| zh-mobile-iphone15 | 关系图渲染 | ✓ | 容器 3 |
| zh-mobile-iphone15 | 零 JS 异常 | ✓ |  |
| zh-mobile-iphone15 | 无非预期 4xx/5xx | ✓ |  |
| zh-mobile-iphonese | 首页加载 | ✓ | http://127.0.0.1:5611/courses |
| zh-mobile-iphonese | 进入课程 | ✓ | http://127.0.0.1:5611/course/6808b11a-74ac-4df9-8e97-c02b4e1030e5/learn |
| zh-mobile-iphonese | 打开知识库浮层 | ✓ |  |
| zh-mobile-iphonese | 知识库加载完成（非固定等待） | ✓ |  |
| zh-mobile-iphonese | 知识树渲染出节点 | ✓ | 67 行 |
| zh-mobile-iphonese | D2 横幅按数据显示（本课有依据→不该出现） | ✓ | count=0 |
| zh-mobile-iphonese | 存在原子知识点 | ✓ |  |
| zh-mobile-iphonese | 知识点详情有内容 | ✓ | 3338 字 |
| zh-mobile-iphonese | D1 来源标签已本地化（无裸值泄漏） | ✓ | 资料来源 |
| zh-mobile-iphonese | 关系图渲染 | ✓ | 容器 3 |
| zh-mobile-iphonese | 零 JS 异常 | ✓ |  |
| zh-mobile-iphonese | 无非预期 4xx/5xx | ✓ |  |

## 全部通过