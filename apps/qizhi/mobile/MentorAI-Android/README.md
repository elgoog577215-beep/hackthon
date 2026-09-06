# MentorAI / 启智 — Android

Android port of the iOS app at `../MentorAI/`. Same backend (`http://jsfzai.zju.edu.cn/api`),
same OAuth flow via ZJU 通行证, same feature set targeted.

Tech stack chosen to mirror the iOS architecture as closely as Compose allows:

- **Language**: Kotlin 1.9.22
- **UI**: Jetpack Compose + Material 3
- **Min SDK**: 26 (Android 8.0)
- **Target / compile SDK**: 34
- **Networking**: OkHttp + okhttp-sse (for chat streaming)
- **JSON**: kotlinx.serialization
- **Token storage**: `EncryptedSharedPreferences` (Keystore-backed)
- **Async**: Coroutines + Flow / StateFlow
- **Navigation**: bottom-nav switch (matches iOS `TabView`)

## Open in Android Studio

1. Install Android Studio Hedgehog (2023.1) or later.
2. `File → Open` → select this `MentorAI-Android/` directory.
3. Let Gradle sync; the IDE will download AGP 8.2.2 + Kotlin 1.9.22 + the Compose BOM.
4. Run the `app` configuration on an emulator or device.

No Gradle wrapper is committed yet — Android Studio will generate one on first sync, or you can
run `gradle wrapper --gradle-version 8.4` from the CLI if you have Gradle installed locally.

## Module map (iOS → Android)

| iOS                              | Android                                                |
|----------------------------------|--------------------------------------------------------|
| `App/MentorAIApp.swift`          | `MentorAIApp.kt` (Application class)                   |
| `App/RootView.swift`             | `app/RootScreen.kt`                                    |
| `App/AppState.swift`             | `app/AppState.kt` (`StateFlow`-driven phase)           |
| `Views/MainTabView.swift`        | `app/MainScreen.kt` (`NavigationBar`)                  |
| `Views/LoginView.swift`          | `views/LoginScreen.kt`                                 |
| `Views/HomeView.swift`           | `views/HomeScreen.kt`                                  |
| `Authentication/*`               | `authentication/*` (TokenStore, AuthAPI, AuthService,  |
|                                  |  AuthWebViewActivity)                                  |
| `Networking/*`                   | `networking/*` (APIClient, APIEnvelope, AuthError)     |
| `User/UserProfile.swift`         | `user/UserProfile.kt`, `user/UserAPI.kt`               |
| `Support/ServerDate.swift`       | `support/ServerDate.kt`                                |
| `Support/Haptics.swift`          | `support/Haptics.kt`                                   |
| `Support/StringEscaping.swift`   | `support/StringEscaping.kt`                            |

## Status

**Done in this scaffold:**

- ✅ Gradle project, AndroidManifest, network security config (mirrors iOS ATS exceptions),
  Material 3 theme matching the ZJU-blue accent.
- ✅ Networking core: `APIClient` over OkHttp with bearer-token GET / POST / form / DELETE and
  envelope unwrapping; typed `AuthError` sealed class.
- ✅ Authentication: OAuth via `AuthWebViewActivity` (intercepts the `code` query param like the
  iOS `AuthWebViewController`), `TokenStore` over `EncryptedSharedPreferences`, `AuthService`
  orchestration (fetch `/auth/url` → present WebView → exchange `code` for JWT via `/auth/callback`).
- ✅ `AppState` with launching/signedOut/signedIn phases, user profile refresh, sign-out.
- ✅ Login screen (gradient + 浙大通行证登录, error banner + alert detail).
- ✅ Profile screen (header + rows + 退出登录 confirm).
- ✅ Support utilities: `ServerDate` (relative + absolute), `Haptics`, `decodingJsonEscapes`
  (for the streamed `\n` chat bug we already mitigated on iOS).

**Chat (just added):**

- ✅ `chat/ChatModels.kt` (`ChatSession`, `ChatMessage`, `ChatRole`, `ChatSendRequest`).
- ✅ `chat/ChatEvent.kt` sealed class mirroring the iOS `ChatEvent`.
- ✅ `chat/SSEStream.kt` — OkHttp-SSE → `Flow<SSEMessage>`, plus the `parseChatEvent`
  extractor that tolerates `type` vs `event`, `content` vs `delta` vs `text`.
- ✅ `chat/SessionAPI.kt` (list / detail / delete).
- ✅ `chat/ChatAPI.kt` — POST `/chat/send` as SSE, streamed as `Flow<ChatEvent>`.
- ✅ `chat/AttachmentAPI.kt` — multipart upload that copies content URIs to cache first.
- ✅ `chat/SessionListViewModel.kt` + `chat/ChatViewModel.kt` (matches iOS state machines
  including the JSON-escape decode of the streamed assistant content).
- ✅ `views/SessionListScreen.kt` (swipe-to-delete via `SwipeToDismissBox`, empty + error states).
- ✅ `views/ChatScreen.kt` (welcome state with suggestion chips, message stack with auto-scroll,
  attachment tray, streaming status banner, input bar with send/stop).
- ✅ `ui/MarkdownText.kt` — Markwon (`io.noties.markwon:core` + tables/strikethrough/tasklist
  /linkify) wrapped via `AndroidView`; renders assistant turns the same way iOS MarkdownUI does.

**Video analysis (just added):**

- ✅ `videoanalysis/VideoModels.kt` (status / operation enums, summary / detail, Zhiyun group + flat
  `ZhiyunCourse`). Raw values stay lowercase to match the server's `OperationEnum` — the lesson
  from the iOS CREATE/lowercase fix is preserved here.
- ✅ `videoanalysis/VideoAnalysisResult.kt` — defensive parser mirroring the iOS one, including
  JSON-string-unwrap for nested fields (teach_summary may arrive as a string, etc.), ordered
  radar axes, donut slices by duration falling back to counts.
- ✅ `videoanalysis/VideoAPI.kt` — list/detail/operate/analyze REST + 5 MB chunked upload + Zhiyun
  flatten + SSE import (id in `end` event, mirrors the iOS fix).
- ✅ `videoanalysis/VideoListViewModel.kt`, `VideoUploadViewModel.kt`, `ZhiyunImportViewModel.kt`.
- ✅ `views/VideoAnalysisListScreen.kt` — grouped by course (same yyyy-MM-dd date regex as iOS),
  swipe-to-delete with confirm, FAB → NewVideoAnalysisScreen, in-tab navigation.
- ✅ `views/NewVideoAnalysisScreen.kt` — Zhiyun / local-video source picker.
- ✅ `views/ZhiyunImportScreen.kt` — date range pickers (Material 3 DatePicker), course-name filter
  applied client-side, grouped course list, import confirmation dialog, importing progress with
  cancel, done state inserts an optimistic `VideoSummary` matching the server name.
- ✅ `views/CustomVideoUploadScreen.kt` — file info, name input, chunk progress, auto-analyze after
  create, gated back button while busy.
- ✅ `views/VideoAnalysisDetailScreen.kt` — status banner, partial-aware messaging during 分析中 /
  失败, auto-poll every 4 s while WAITING (matches iOS schedulePolling), menu with
  refresh/重新分析/删除. The chart sections currently render as labeled rows; full canvas chart
  visuals (radar / donut / word cloud / volume waveform) ship in the next sub-turn.

**Video detail charts (just added):**

- ✅ `ui/charts/ReportPalette.kt` — shared color palette + `reportClock` helper.
- ✅ `ui/charts/RadarChart.kt` — Canvas polygon with 5 grid rings, spokes, vertices, labeled
  scores, tap-to-select with center-pill readout.
- ✅ `ui/charts/DonutChart.kt` — Canvas arcs with tap-to-select (pops slice, dims others, shows
  centered percent) + `FlowRow` legend chips that mirror the selection.
- ✅ `ui/charts/VolumeChart.kt` — line + dashed average chart with horizontal scrub / tap to
  pin a sample, time-coded inspector readout.
- ✅ `ui/charts/WordCloud.kt` — Archimedean-spiral layout with the same occupancy grid as iOS,
  draws via Compose Canvas + `TextMeasurer`.
- ✅ `ui/charts/TeachTimeline.kt` — vertical timeline with dot + connector line (uses
  `IntrinsicSize.Min` so the connector stretches to content), optional search highlight.
- ✅ `ui/charts/TranscriptRow.kt` — monospaced time range + text with highlight overlay.
- ✅ `views/TranscriptFullScreen.kt` + `views/TeachSummaryFullScreen.kt` — full-screen pushes
  with an inline search field, mirroring iOS `searchable`.
- ✅ `ui/VideoPlayerView.kt` — ExoPlayer (Media3 1.2.1) wrapped via `AndroidView`; URL resolver
  mirrors iOS `videoURL(for:)` (handles full URLs, `/static/...`, raw `uploads/...`).
- ✅ `views/VideoAnalysisDetailScreen.kt` — rewritten to use all of the above, with in-screen
  navigation to the full transcript / summary screens. Auto-poll retained.

**Still to port:**

- Resource generation (outline, teaching plan, PPT, question bank flows).
- Final theming sweep / TightLabelStyle equivalent for chips.

The app is now fully navigable end-to-end: login → bottom nav → chat + video list/import/upload
+ profile.
