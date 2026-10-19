<template>
  <section class="student-courses" :class="{ 'is-compact': compact }">
    <header class="course-library-heading">
      <div>
        <h1>
          {{
            unified
              ? t("workspaceUi.myCourses")
              : copy("教师授权课程", "Authorized courses")
          }}
        </h1>
        <p>{{ t("workspaceUi.courseHelp") }}</p>
      </div>
      <div class="library-heading-actions">
        <button type="button" :disabled="loading" @click="load">
          {{ copy("刷新", "Refresh") }}</button
        ><button
          v-if="unified"
          type="button"
          class="primary"
          data-testid="student-create-handout"
          @click="emit('create', 'systematic')"
        >
          <Plus :size="16" />{{ t("workspaceUi.newCourse") }}
        </button>
      </div>
    </header>
    <div class="library-filters">
      <label class="library-search"
        ><Search :size="17" /><input
          v-model="query"
          type="search"
          :placeholder="t('workspaceUi.searchCourses')"
          :aria-label="t('workspaceUi.searchCourses')"
      /></label>
      <div
        v-if="unified"
        class="library-filter-tabs"
        role="group"
        :aria-label="t('workspaceUi.myCourses')"
      >
        <button
          v-for="item in filters"
          :key="item.id"
          type="button"
          :aria-pressed="filter === item.id"
          @click="selectFilter(item.id)"
        >
          {{ item.label }}
        </button>
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
        :origin="t('workspaceUi.teacherOrigin')"
      >
        <template #title
          ><RouterLink
            v-if="course.reading_available"
            :to="studentCourseLink(course.course_id)"
            >{{ course.title }}</RouterLink
          ><span v-else>{{ course.title }}</span></template
        >
        <template #summary
          ><span v-if="course.question_count !== undefined"
            >{{ course.question_count }}
            {{ copy("道课程练习", "course exercises") }}</span
          ></template
        >
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
                <button
                  type="button"
                  :disabled="loading"
                  @click="derive(course)"
                >
                  {{
                    copy(
                      "生成个人复习讲义",
                      "Create a personal revision handout",
                    )
                  }}
                </button>
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
              <button
                type="button"
                class="course-detail-toggle"
                :aria-expanded="detailCourseId === course.course_id"
                @click="
                  detailCourseId =
                    detailCourseId === course.course_id ? '' : course.course_id
                "
              >
                {{ t("studentWorkspace.coursePath") }}
              </button>
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
              <button :disabled="loading" @click="update(course)">
                {{ copy("使用新版本", "Use new version") }}
              </button>
            </div>
            <section
              v-if="course.published_ppts?.length"
              class="published-ppts"
            >
              <h3>{{ copy("教师发布的 PPT", "Published PPTs") }}</h3>
              <button
                v-for="ppt in course.published_ppts"
                :key="ppt.asset_id"
                :disabled="loading"
                @click="downloadPpt(course, ppt.asset_id, ppt.filename)"
              >
                {{ copy("下载", "Download") }} {{ ppt.filename }}
              </button>
            </section>
            <button
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
              }}</button
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
        :origin="t('workspaceUi.ownedOrigin')"
      >
        <template #title
          ><RouterLink :to="`/study/${encodeURIComponent(item.id)}`">{{
            item.title
          }}</RouterLink></template
        >
        <template #summary
          ><span
            >{{ c(item.purpose) }} · {{ statusLabel(item.status) }}</span
          ></template
        >
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
                "还没有获授权课程。将你的学生身份提供给教师，教师授权后课程会显示在这里。",
                "No authorized courses yet. Give your student identity to your teacher; granted courses will appear here.",
              )
      }}
    </p>
    <details class="student-id">
      <summary>{{ copy("我的学生身份", "My student identity") }}</summary>
      <code>{{ userId }}</code>
    </details>
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { ArrowRight, Plus, Search } from "lucide-vue-next";
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
const loading = computed(() => reading.value || acting.value);
const filters = computed(() => [
  { id: "all" as const, label: t("workspaceUi.allCourses") },
  { id: "teacher" as const, label: t("workspaceUi.teacherCourses") },
  { id: "owned" as const, label: t("workspaceUi.ownedCourses") },
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
function selectFilter(value: "all" | "teacher" | "owned") {
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
  max-width: 1320px;
  box-sizing: border-box;
  margin: auto;
  padding: 36px;
  color: var(--lz-text);
  font-size: 15px;
}
.course-library-heading,
.library-heading-actions,
.library-filters,
.library-search {
  display: flex;
  align-items: center;
  gap: 14px;
}
.course-library-heading {
  justify-content: space-between;
}
h1 {
  margin: 0;
  font-size: 28px;
  font-weight: 650;
  line-height: 1.4;
  color: var(--lz-text-strong);
}
p {
  margin: 8px 0 0;
  color: var(--lz-text-secondary);
  line-height: 1.7;
}
button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 36px;
  padding: 7px 12px;
  border: 1px solid var(--lz-border);
  border-radius: var(--lz-radius-control);
  background: white;
  color: var(--lz-text);
  font: inherit;
  cursor: pointer;
}
button.primary {
  background: var(--lz-action-primary-bg);
  color: var(--lz-action-primary-text);
  border-color: var(--lz-action-primary-border);
  box-shadow: var(--lz-action-shadow);
}
.library-filters {
  margin: 26px 0 22px;
  flex-wrap: wrap;
}
.library-search {
  flex: 0 1 330px;
  box-sizing: border-box;
  gap: 9px;
  min-width: 240px;
  color: var(--lz-text-muted);
  padding: 8px 12px;
  border: 1px solid var(--lz-border);
  border-radius: var(--lz-radius-control);
  background: white;
}
.library-search input {
  padding: 0;
  line-height: 24px;
  min-width: 0;
  width: 100%;
  border: 0;
  outline: none;
  font: inherit;
  color: var(--lz-text);
  background: transparent;
}
.library-search:focus-within {
  outline: 2px solid var(--lz-brand);
  outline-offset: 2px;
}
.library-filter-tabs {
  display: flex;
  padding: 3px;
  border-radius: var(--lz-radius-control);
  background: transparent;
}
.library-filter-tabs button {
  border: 0;
  background: transparent;
  color: var(--lz-text-secondary);
}
.library-filter-tabs button[aria-pressed="true"] {
  background: var(--lz-brand-soft);
  color: var(--lz-brand-strong);
  box-shadow: none;
}
.course-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 20px;
  align-items: start;
}
.course-start {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  color: var(--lz-brand-strong);
  font-weight: 600;
  text-decoration: none;
}
.course-resources {
  margin-top: 16px;
  border-top: 1px solid var(--lz-border);
  padding-top: 14px;
}
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
  padding: 32px 0;
}
.student-id {
  margin-top: 24px;
  color: var(--lz-text-secondary);
}
.student-id summary {
  cursor: pointer;
}
.student-id code {
  display: block;
  margin-top: 10px;
  overflow-wrap: anywhere;
}
[role="alert"] {
  color: var(--lz-danger);
}
a:focus-visible,
button:focus-visible,
summary:focus-visible {
  outline: 2px solid var(--lz-brand);
  outline-offset: 3px;
}
button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
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
</style>
