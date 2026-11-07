<template>
  <section class="student-courses" :class="{ 'is-compact': compact }">
    <header v-if="!unified" class="course-library-heading"><h1>{{ copy('教师授权课程', 'Authorized courses') }}</h1></header>
    <div class="library-filters">
      <ElInput
        v-model="query"
        class="library-search"
        size="large"
        type="search"
        clearable
        :placeholder="t('workspaceUi.searchCourses')"
        :aria-label="t('workspaceUi.searchCourses')"
      ><template #prefix><Search :size="17" /></template></ElInput>
      <UiSelectMenu
        v-if="unified"
        class="library-filter-tabs"
        :label="copy('来源', 'Source')"
        :model-value="filter"
        :options="filters"
        :accessibility-label="copy('按课程来源筛选', 'Filter by course source')"
        @update:model-value="selectFilter"
      />
      <div class="library-heading-actions">
        <ElButton class="library-refresh" native-type="button" :disabled="loading" :aria-label="copy('刷新', 'Refresh')" :title="copy('刷新', 'Refresh')" @click="unified ? emit('refresh') : load()">
          <RefreshCw :size="16" aria-hidden="true" /><span class="library-refresh-label">{{ copy("刷新", "Refresh") }}</span></ElButton
        ><ElButton
          v-if="unified"
          native-type="button"
          type="primary"
          data-testid="student-create-handout"
          @click="emit('create', 'systematic')"
        >
          <Plus :size="16" />{{ t("workspaceUi.newCourse") }}
        </ElButton>
      </div>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">
      {{ copy("正在读取课程…", "Loading courses…") }}
    </p>
    <div
      v-if="visibleCourses.length || visibleMaterials.length"
      class="course-grid"
    >
      <CourseLibraryCard
        v-for="course in visibleCourses"
        :key="`teacher:${course.course_id}`"
        :course-id="course.course_id"
        :title="course.title"
      >
        <template #title
          ><RouterLink
            v-if="course.reading_available"
            :to="studentCourseLink(course.course_id)"
            >{{ course.title }}</RouterLink
          ><span v-else>{{ course.title }}</span></template
        >
        <p class="course-source-label">{{ t("workspaceUi.teacherCourses") }}</p>
        <p v-if="course.update_available" class="update-hint">
          {{ copy("教师发布了新版本", "Your teacher published an update") }}
        </p>
        <p v-if="!course.reading_available">
          {{
            copy(
              "教师尚未提供讲义",
              "The teacher has not provided a handout yet",
            )
          }}
        </p>
        <template #actions
          ><RouterLink
            v-if="course.reading_available"
            class="course-start"
            :to="studentCourseLink(course.course_id)"
            >{{ t("workspaceUi.readCourse")
            }}<ArrowRight :size="16" /></RouterLink
        ></template>
        <template #details>
          <details
            v-if="derivedFor(course.course_id).length"
            class="course-resources personal-course-materials"
          >
            <summary>
              {{ t("workspaceUi.courseMaterials") }} ·
              {{ derivedFor(course.course_id).length }}
            </summary>
            <RouterLink
              v-for="item in derivedFor(course.course_id)"
              :key="item.id"
              :to="`/study/${encodeURIComponent(item.id)}`"
              >{{ item.title }}</RouterLink
            >
          </details>
          <details class="course-resources">
            <summary>{{ t("workspaceUi.courseDetails") }}</summary>
            <template v-if="course.reading_available">
              <div class="course-card-actions">
                <ElButton
                  native-type="button"
                  :disabled="loading"
                  @click="derive(course)"
                >
                  {{
                    copy(
                      "生成个人复习讲义",
                      "Create a personal revision handout",
                    )
                  }}
                </ElButton>
              </div>
              <nav
                class="course-tools"
                :aria-label="`${course.title} · ${t('studentWorkspace.courseTools')}`"
              >
                <RouterLink
                  v-for="tool in tools"
                  :key="tool"
                  :to="studentCourseLink(course.course_id, tool)"
                  >{{ t(`studentWorkspace.${tool}`) }}</RouterLink
                >
              </nav>
              <ElButton
                native-type="button"
                class="course-detail-toggle"
                :aria-expanded="detailCourseId === course.course_id"
                @click="
                  detailCourseId =
                    detailCourseId === course.course_id ? '' : course.course_id
                "
              >
                {{ t("studentWorkspace.coursePath") }}
              </ElButton>
              <StudentLearningPath
                compact
                v-if="detailCourseId === course.course_id"
                :key="`${course.course_id}:${course.revision_id}:${pathGeneration}`"
                :course-id="course.course_id"
                :title="course.title"
              />
            </template>
            <p v-else>
              {{
                copy(
                  "教师尚未提供讲义",
                  "The teacher has not provided a handout yet",
                )
              }}
            </p>
            <div v-if="course.update_available" class="course-update">
              <strong>{{
                copy("教师发布了新版本", "Your teacher published an update")
              }}</strong>
              <p>
                {{
                  copy(
                    "更新后继续学习，原作答与笔记保留。",
                    "Continue with the new version; previous attempts and notes are retained.",
                  )
                }}
              </p>
              <ElButton :disabled="loading" @click="update(course)">
                {{ copy("使用新版本", "Use new version") }}
              </ElButton>
            </div>
            <section
              v-if="course.published_ppts?.length"
              class="published-ppts"
            >
              <h3>{{ copy("教师发布的 PPT", "Published PPTs") }}</h3>
              <ElButton
                v-for="ppt in course.published_ppts"
                :key="ppt.asset_id"
                :disabled="loading"
                @click="downloadPpt(course, ppt.asset_id, ppt.filename)"
              >
                {{ copy("下载", "Download") }} {{ ppt.filename }}
              </ElButton>
            </section>
            <ElButton
              v-if="course.exchange_origin"
              class="feedback-button"
              :aria-expanded="feedbackCourse === course.course_id"
              @click="
                feedbackCourse =
                  feedbackCourse === course.course_id ? '' : course.course_id
              "
            >
              {{
                copy("课程提问与教师回复", "Questions & teacher replies")
              }}</ElButton
            ><StudentCourseFeedback
              v-if="
                course.exchange_origin && feedbackCourse === course.course_id
              "
              :course-id="course.course_id"
              :revision-id="course.revision_id"
            /></details
        ></template>
      </CourseLibraryCard>
      <CourseLibraryCard
        v-for="item in visibleMaterials"
        :key="`personal:${item.id}`"
        :course-id="item.id"
        :title="item.title"
      >
        <template #title
          ><RouterLink :to="`/study/${encodeURIComponent(item.id)}`">{{
            item.title
          }}</RouterLink></template
        >
        <p class="course-source-label">{{ t("workspaceUi.ownedCourses") }} · {{ c(item.purpose) }}</p>
        <p v-if="item.status !== 'completed'" role="status">{{ statusLabel(item.status) }}</p>
        <template #actions
          ><RouterLink
            class="course-start"
            :to="`/study/${encodeURIComponent(item.id)}`"
            >{{ t("workspaceUi.readCourse")
            }}<ArrowRight :size="16" /></RouterLink
        ></template>
      </CourseLibraryCard>
    </div>
    <p
      v-else-if="!loading && (!error || filter === 'owned')"
      class="course-empty"
    >
      {{
        query || filter !== "all"
          ? t("workspaceUi.noMatch")
          : unified
            ? t("workspaceUi.emptyCourses")
            : copy(
                "还没有获授权课程，教师发布并授权后会显示在这里。",
                "No authorized courses yet. Courses appear here after your teacher publishes and grants access.",
              )
      }}
    </p>
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { ElButton, ElInput } from "element-plus";
import UiSelectMenu from "./UiSelectMenu.vue";
import { ArrowRight, Plus, RefreshCw, Search } from "lucide-vue-next";
import {
  studyApi,
  type StudyCourse,
  type StudySource,
  type StudySummary,
  type StudyPurpose,
} from "../api/study";
import { activeLocale, t } from "../shared/i18n";
import { studyCopy as c, type StudyCopyKey } from "../shared/study-copy";
import StudentLearningPath from "./StudentLearningPath.vue";
import CourseLibraryCard from "./CourseLibraryCard.vue";
import {
  studentCourseLink,
  type StudentWorkspaceTool,
} from "../shared/student-workspace";
import StudentCourseFeedback from "./StudentCourseFeedback.vue";

const props = withDefaults(
  defineProps<{
    userId: string;
    refreshing?: boolean;
    compact?: boolean;
    unified?: boolean;
    materials?: StudySummary[];
    initialFilter?: "all" | "teacher" | "owned";
  }>(),
  { compact: false, unified: false, initialFilter: "all" },
);
const emit = defineEmits<{
  source: [source: StudySource];
  create: [purpose: StudyPurpose];
  refresh: [];
  filter: [value: "all" | "teacher" | "owned"];
}>();
const copy = (zh: string, en: string) =>
  activeLocale.value === "en" ? en : zh;
const detailCourseId = ref(""),
  feedbackCourse = ref(""),
  pathGeneration = ref(0);
const tools: StudentWorkspaceTool[] = [
  "practice",
  "mistakes",
  "knowledge",
  "overview",
];
const courses = ref<StudyCourse[]>([]),
  reading = ref(false),
  acting = ref(false),
  error = ref(""),
  query = ref("");
const filter = ref(props.initialFilter),
  materialsOwner = ref("");
const loading = computed(() => reading.value || acting.value || props.refreshing);
const filters = computed(() => [
  { value: "all" as const, label: t("workspaceUi.allCourses") },
  { value: "teacher" as const, label: t("workspaceUi.teacherCourses") },
  { value: "owned" as const, label: t("workspaceUi.ownedCourses") },
]);
const matches = (title: string) =>
  title.toLocaleLowerCase().includes(query.value.trim().toLocaleLowerCase());
const visibleCourses = computed(() =>
  filter.value === "owned"
    ? []
    : courses.value.filter((course) => matches(course.title)),
);
const ownedMaterials = computed(() =>
  props.unified && materialsOwner.value === props.userId
    ? props.materials || []
    : [],
);
const visibleMaterials = computed(() =>
  filter.value === "teacher"
    ? []
    : ownedMaterials.value.filter(
        (item) =>
          matches(item.title) &&
          (filter.value === "owned" ||
            !item.source_course_ids?.some((id) =>
              visibleCourses.value.some((course) => course.course_id === id),
            )),
      ),
);
function derivedFor(courseId: string) {
  return ownedMaterials.value.filter((item) =>
    item.source_course_ids?.includes(courseId),
  );
}
const statusLabel = (status: string) =>
  c(
    (["pending", "running", "completed", "failed", "paused"].includes(status)
      ? status
      : "draft") as StudyCopyKey,
  );
watch(
  () => props.initialFilter,
  (value) => {
    filter.value = value;
  },
);
watch(
  [() => props.userId, () => props.materials],
  ([owner, provided], previous) => {
    materialsOwner.value =
      previous && owner !== previous[0] && provided === previous[1]
        ? ""
        : owner;
  },
  { immediate: true, flush: "sync" },
);
function selectFilter(value: string) {
  if (value !== "all" && value !== "teacher" && value !== "owned") return;
  filter.value = value;
  emit("filter", value);
}
let sequence = 0,
  ownerEpoch = 0,
  disposed = false;
let controller: AbortController | undefined;
async function load() {
  const current = ++sequence,
    owner = props.userId,
    epoch = ownerEpoch;
  controller?.abort();
  controller = new AbortController();
  reading.value = true;
  error.value = "";
  const valid = () =>
    !disposed &&
    current === sequence &&
    epoch === ownerEpoch &&
    owner === props.userId;
  try {
    const result = await studyApi.courses(controller.signal);
    if (!Array.isArray(result))
      throw new Error(t("workspaceUi.invalidCourseList"));
    if (valid()) {
      courses.value = result;
      if (!result.some((course) => course.course_id === detailCourseId.value))
        detailCourseId.value = "";
      pathGeneration.value++;
    }
  } catch (cause) {
    if (valid())
      error.value =
        cause instanceof Error
          ? cause.message
          : copy("课程读取失败", "Could not load courses");
  } finally {
    if (valid()) reading.value = false;
  }
}
watch(
  () => props.userId,
  (owner) => {
    ownerEpoch++;
    sequence++;
    controller?.abort();
    courses.value = [];
    detailCourseId.value = "";
    feedbackCourse.value = "";
    error.value = "";
    acting.value = false;
    reading.value = false;
    if (owner) void load();
  },
  { immediate: true, flush: "sync" },
);
async function runAction(operation: (valid: () => boolean) => Promise<void>) {
  if (acting.value || !props.userId) return;
  const owner = props.userId,
    epoch = ownerEpoch;
  const valid = () =>
    !disposed && epoch === ownerEpoch && props.userId === owner;
  acting.value = true;
  error.value = "";
  try {
    await operation(valid);
  } catch (cause) {
    if (valid())
      error.value =
        cause instanceof Error ? cause.message : c("requestFailure");
  } finally {
    if (valid()) acting.value = false;
  }
}
function derive(course: StudyCourse) {
  return runAction(async (valid) => {
    const source = await studyApi.courseSource(
      course.course_id,
      course.revision_id,
    );
    if (valid()) emit("source", source);
  });
}
function update(course: StudyCourse) {
  return runAction(async (valid) => {
    await studyApi.updateCourse(course.course_id, course.revision_id);
    if (valid()) await load();
  });
}
function downloadPpt(course: StudyCourse, assetId: string, filename: string) {
  return runAction(async (valid) => {
    const blob = await studyApi.coursePpt(
      course.course_id,
      assetId,
      course.revision_id,
    );
    if (!valid()) return;
    const url = URL.createObjectURL(blob),
      link = document.createElement("a");
    try {
      link.href = url;
      link.download = filename;
      link.click();
    } finally {
      URL.revokeObjectURL(url);
    }
  });
}
defineExpose({ reload: load });
onBeforeUnmount(() => {
  disposed = true;
  sequence++;
  ownerEpoch++;
  controller?.abort();
});
</script>
<style scoped>
.student-courses {
  max-width: 1408px;
  box-sizing: border-box;
  margin: auto;
  padding: 24px clamp(20px, 3.2vw, 44px) 40px;
  color: var(--lz-text);
  font-size: 15px;
}
.course-library-heading,
.library-heading-actions,
.library-filters {
  display: flex;
  align-items: center;
  gap: 10px;
}
.course-library-heading {
  justify-content: space-between;
}
h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 650;
  line-height: 1.4;
  color: var(--lz-text-strong);
}
p {
  margin: 8px 0 0;
  color: var(--lz-text-secondary);
  line-height: 1.7;
}
.library-heading-actions { margin-left: auto; }
.student-courses .library-heading-actions :deep(.el-button) {
  height: 40px;
  min-height: 40px;
  font-size: 15px;
}
.library-heading-actions :deep(.el-button > span) { gap: 6px; }
.library-filters {
  margin: 0 0 18px;
  flex-wrap: wrap;
}
.course-grid {
  overflow: hidden;
  border: 1px solid var(--lz-border);
  border-radius: 12px;
  background: var(--lz-surface);
  box-shadow: 0 1px 2px rgba(30, 41, 59, .025);
}
.course-start {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid var(--lz-brand-border, #c7d2fe);
  border-radius: 8px;
  background: var(--lz-surface);
  white-space: nowrap;
  color: var(--lz-brand-strong);
  font-weight: 600;
  text-decoration: none;
}
.course-start:hover { background: var(--lz-brand-soft); border-color: var(--lz-brand); }
.course-resources {
  margin-top: 12px;
  padding-top: 8px;
}
.course-resources[open] { border-top: 1px solid var(--lz-border); padding-top: 14px; }
.personal-course-materials a {
  display: block;
  padding: 10px 0;
  color: var(--lz-brand-strong);
  text-decoration: none;
  font-size: 15px;
}
.course-resources summary {
  cursor: pointer;
  font-size: 15px;
  color: var(--lz-text-secondary);
}
.course-card-actions,
.course-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}
.course-tools a {
  color: var(--lz-brand-strong);
  text-decoration: none;
}
.course-detail-toggle,
.feedback-button {
  margin-top: 14px;
}
.course-update,
.published-ppts {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--lz-border);
}
.published-ppts h3 {
  margin: 0 0 10px;
  font-size: 15px;
}
.course-update button {
  margin-top: 10px;
}
.update-hint {
  color: var(--lz-brand-strong);
}
.course-empty {
  min-height: 300px;
  display: grid;
  place-content: center;
  text-align: center;
  padding: 32px;
}
[role="alert"] {
  color: var(--lz-danger);
}
a:focus-visible,
summary:focus-visible {
  outline: 2px solid var(--lz-brand);
  outline-offset: 3px;
}
@media (max-width: 760px) {
  .course-library-heading {
    align-items: start;
    flex-wrap: wrap;
  }
  .student-courses {
    padding: 18px 16px 24px;
  }
  .library-filters {
    align-items: stretch;
    gap: 10px;
    margin-bottom: 16px;
  }
  .library-search {
    flex: 1 1 100%;
    min-width: 0;
  }
  .library-search :deep(.el-input__wrapper) {
    min-height: 44px;
    box-sizing: border-box;
  }
  .library-heading-actions {
    margin-left: auto;
    gap: 8px;
  }
  .student-courses :deep(.el-button) {
    min-height: 44px;
  }
  .course-start,
  .course-detail-toggle,
  .feedback-button {
    min-height: 44px;
  }
  .course-resources summary {
    min-height: 44px;
    display: flex;
    align-items: center;
  }
  .course-tools a {
    min-height: 44px;
    display: inline-flex;
    align-items: center;
    padding-inline: 6px;
  }
}
.library-search { flex: 1 1 360px; min-width: 240px; }
.library-search :deep(.el-input__wrapper) { min-height: 40px; box-sizing: border-box; background: var(--lz-surface); border-radius: 9px; box-shadow: 0 0 0 1px var(--lz-border) inset; }
.library-search :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 1px var(--lz-brand) inset, 0 0 0 3px color-mix(in srgb, var(--lz-brand) 12%, transparent); }
.library-filter-tabs { width: 200px; flex: 0 0 200px; }
.library-filter-tabs :deep(.ui-select-menu__trigger) {
  min-height: 40px;
  height: 40px;
  grid-template-columns: minmax(0, 1fr) 15px;
  border-radius: 9px;
}
.library-filter-tabs :deep(.ui-select-menu__copy small) { display: none; }
.library-filter-tabs :deep(.ui-select-menu__copy strong) { font-weight: 600; }
@media (max-width: 760px) {
  .library-search { flex-basis: 100%; min-width: 0; }
  .library-search :deep(.el-input__wrapper),
  .library-filter-tabs :deep(.ui-select-menu__trigger),
  .student-courses .library-heading-actions :deep(.el-button) { height: 44px; min-height: 44px; }
  .library-filter-tabs { flex: 1; min-width: 100px; }
  .library-heading-actions { gap: 8px; }
  .library-heading-actions .library-refresh { width: 44px; padding-inline: 0; }
  .library-refresh-label { display: none; }
}
@media (max-width: 480px) {
  .course-grid :deep(.course-library-card__heading),
  .course-grid :deep(.course-library-card__summary),
  .course-grid :deep(.course-library-card__actions) { grid-column: 1 / -1; }
  .course-grid :deep(.course-library-card__actions) { grid-row: auto; }
}
.student-courses :deep(.el-button + .el-button) { margin-left: 0; }
</style>
