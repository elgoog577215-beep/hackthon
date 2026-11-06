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
      <UiSegmentedControl
        v-if="unified"
        class="library-filter-tabs"
        :model-value="filter"
        :options="filters"
        :accessibility-label="t('workspaceUi.myCourses')"
        @update:model-value="selectFilter"
      />
      <div class="library-heading-actions">
        <ElButton native-type="button" :disabled="loading" @click="load">
          {{ copy("刷新", "Refresh") }}</ElButton
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
        <template #title><span>{{ course.title }}</span></template>
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
        <template #actions>
          <RouterLink
            v-if="course.reading_available"
            class="course-start"
            :to="studentCourseLink(course.course_id)"
          >
            {{ t("workspaceUi.readCourse") }}<ArrowRight :size="15" />
          </RouterLink>
        </template>
        <template #menu>
          <details
            v-if="hasCourseOptions(course)"
            class="course-actions-menu"
            @keydown.esc="closeMenu"
          >
            <summary :aria-label="copy('更多课程选项', 'More course options')">
              <MoreHorizontal :size="18" />
            </summary>
            <div class="course-actions-menu__panel">
              <button
                v-if="course.reading_available"
                type="button"
                :aria-expanded="detailCourseId === course.course_id"
                @click="chooseMenuAction($event, () => toggleCoursePath(course.course_id))"
              >
                {{ t("studentWorkspace.coursePath") }}
              </button>
              <button
                v-if="course.reading_available"
                type="button"
                :disabled="acting || loading"
                @click="chooseMenuAction($event, () => derive(course))"
              >
                {{ copy("生成复习讲义", "Create revision handout") }}
              </button>
              <button
                v-if="derivedFor(course.course_id).length"
                type="button"
                data-testid="student-course-materials-toggle"
                @click="chooseMenuAction($event, () => toggleCourseMaterials(course.course_id))"
              >
                {{ t("workspaceUi.courseMaterials") }} ·
                {{ derivedFor(course.course_id).length }}
              </button>
              <button
                v-if="course.update_available"
                type="button"
                :disabled="acting || loading"
                @click="chooseMenuAction($event, () => update(course))"
              >
                {{ copy("使用新版本", "Use new version") }}
              </button>
              <button
                v-for="ppt in course.published_ppts || []"
                :key="ppt.asset_id"
                type="button"
                :disabled="acting || loading"
                @click="chooseMenuAction($event, () => downloadPpt(course, ppt.asset_id, ppt.filename))"
              >
                {{ copy("下载", "Download") }} · {{ ppt.filename }}
              </button>
              <button
                v-if="course.exchange_origin"
                type="button"
                :aria-expanded="feedbackCourse === course.course_id"
                @click="chooseMenuAction($event, () => toggleCourseFeedback(course.course_id))"
              >
                {{ copy("课程提问与教师回复", "Questions & teacher replies") }}
              </button>
            </div>
          </details>
        </template>
        <template #details>
          <section
            v-if="materialsCourseId === course.course_id"
            class="course-card-panel personal-course-materials"
          >
            <h3>{{ t("workspaceUi.courseMaterials") }}</h3>
            <RouterLink
              v-for="item in derivedFor(course.course_id)"
              :key="item.id"
              :to="`/study/${encodeURIComponent(item.id)}`"
            >{{ item.title }}</RouterLink>
          </section>
          <StudentLearningPath
            v-if="detailCourseId === course.course_id"
            compact
            class="course-card-panel"
            :key="`${course.course_id}:${course.revision_id}:${pathGeneration}`"
            :course-id="course.course_id"
            :title="course.title"
          />
          <StudentCourseFeedback
            v-if="course.exchange_origin && feedbackCourse === course.course_id"
            class="course-card-panel"
            :course-id="course.course_id"
            :revision-id="course.revision_id"
          />
        </template>
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
        <p v-if="item.status !== 'completed'" role="status">{{ statusLabel(item.status) }}</p>
        <template #actions>
          <RouterLink
            class="course-start"
            :to="`/study/${encodeURIComponent(item.id)}`"
          >
            {{ t("workspaceUi.readCourse") }}<ArrowRight :size="15" />
          </RouterLink>
        </template>
        <template #menu>
          <details class="course-actions-menu">
            <summary :aria-label="copy('更多课程选项', 'More course options')">
              <MoreHorizontal :size="18" />
            </summary>
            <div class="course-actions-menu__panel">
              <button
                type="button"
                :disabled="item.status !== 'completed' || acting || loading"
                :title="item.status === 'completed' ? undefined : copy('讲义完成后可下载', 'Available after the handout is complete')"
                @click="chooseMenuAction($event, () => exportHandout(item))"
              >
                {{ copy("下载讲义", "Download handout") }}
              </button>
            </div>
          </details>
        </template>
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
import UiSegmentedControl from "./UiSegmentedControl.vue";
import { ArrowRight, MoreHorizontal, Plus, Search } from "lucide-vue-next";
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
import { studentCourseLink } from "../shared/student-workspace";
import StudentCourseFeedback from "./StudentCourseFeedback.vue";

const props = withDefaults(
  defineProps<{
    userId: string;
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
  filter: [value: "all" | "teacher" | "owned"];
}>();
const copy = (zh: string, en: string) =>
  activeLocale.value === "en" ? en : zh;
const detailCourseId = ref(""),
  materialsCourseId = ref(""),
  feedbackCourse = ref(""),
  pathGeneration = ref(0);
const courses = ref<StudyCourse[]>([]),
  reading = ref(false),
  acting = ref(false),
  error = ref(""),
  query = ref("");
const filter = ref(props.initialFilter),
  materialsOwner = ref("");
const loading = computed(() => reading.value || acting.value);
const filters = computed(() => [
  {
    value: "all" as const,
    label: activeLocale.value === "en" ? "All" : t("workspaceUi.allCourses"),
    title: t("workspaceUi.allCourses"),
  },
  {
    value: "teacher" as const,
    label: activeLocale.value === "en" ? "Teacher" : t("workspaceUi.teacherCourses"),
    title: t("workspaceUi.teacherCourses"),
  },
  {
    value: "owned" as const,
    label: activeLocale.value === "en" ? "Mine" : t("workspaceUi.ownedCourses"),
    title: t("workspaceUi.ownedCourses"),
  },
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
      if (!result.some((course) => course.course_id === materialsCourseId.value))
        materialsCourseId.value = "";
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
    materialsCourseId.value = "";
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
function chooseMenuAction(event: Event, action: () => unknown) {
  const menu = (event.currentTarget as HTMLElement).closest<HTMLDetailsElement>(
    ".course-actions-menu",
  );
  if (menu) menu.open = false;
  void action();
}
function closeMenu(event: KeyboardEvent) {
  (event.currentTarget as HTMLDetailsElement).open = false;
}
function hasCourseOptions(course: StudyCourse) {
  return Boolean(
    course.reading_available ||
      course.update_available ||
      course.published_ppts?.length ||
      course.exchange_origin,
  );
}
function toggleCoursePath(courseId: string) {
  detailCourseId.value = detailCourseId.value === courseId ? "" : courseId;
}
function toggleCourseMaterials(courseId: string) {
  materialsCourseId.value = materialsCourseId.value === courseId ? "" : courseId;
}
function toggleCourseFeedback(courseId: string) {
  feedbackCourse.value = feedbackCourse.value === courseId ? "" : courseId;
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
function exportHandout(item: StudySummary) {
  return runAction(async (valid) => {
    const blob = await studyApi.export(item.id);
    if (!valid()) return;
    const url = URL.createObjectURL(blob),
      link = document.createElement("a");
    try {
      link.href = url;
      link.download = `${item.title}.md`;
      link.click();
    } finally {
      URL.revokeObjectURL(url);
    }
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
  max-width: 1320px;
  box-sizing: border-box;
  margin: auto;
  padding: 36px;
  color: var(--lz-text);
  font-size: 15px;
}
.course-library-heading,
.library-heading-actions,
.library-filters {
  display: flex;
  align-items: center;
  gap: 14px;
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
.library-filters {
  margin: 0 0 22px;
  flex-wrap: wrap;
}
.course-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 20px;
  align-items: stretch;
}
.course-library-card__meta :deep(p) {
  overflow: hidden;
  margin: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.course-start {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
.course-card-panel {
  min-width: 0;
  margin: 0;
  padding: 12px;
}
.personal-course-materials a {
  display: block;
  padding: 6px 0;
  color: var(--lz-brand-strong);
  text-decoration: none;
  font-size: 14px;
}
.personal-course-materials { display: grid; gap: 2px; }
.personal-course-materials h3 {
  margin: 0 0 4px;
  color: var(--lz-text-secondary);
  font-size: 14px;
  font-weight: 600;
}
.update-hint {
  color: var(--lz-brand-strong);
}
.course-empty {
  padding: 32px 0;
}
[role="alert"] {
  color: var(--lz-danger);
}
a:focus-visible,
summary:focus-visible {
  outline: 2px solid var(--lz-brand);
  outline-offset: 3px;
}
@media (max-width: 1150px) {
  .course-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 760px) {
  .course-grid {
    grid-template-columns: 1fr;
  }
  .course-library-heading {
    align-items: start;
    flex-wrap: wrap;
  }
  .student-courses {
    padding: 24px;
  }
}
.library-search { flex: 0 1 330px; min-width: 240px; }
.library-filter-tabs { --ui-segment-font-size: 15px; }
.student-courses :deep(.el-button + .el-button) { margin-left: 0; }
@media (max-width: 380px) {
  .student-courses { padding: 16px; }
}
</style>
