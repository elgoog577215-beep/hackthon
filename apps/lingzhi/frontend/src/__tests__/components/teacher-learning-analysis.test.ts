import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/utils/http", () => ({
  default: api,
  teacherReadRequestConfig: (config: object) => ({
    ...config,
    identityScope: "teacher",
  }),
}));
import TeacherLearningAnalysis from "@/components/TeacherLearningAnalysis.vue";
import { setLocale } from "@/shared/i18n";
import zh from "../../../public/locales/zh/translation.json";
import en from "../../../public/locales/en/translation.json";
let wrapper: VueWrapper | undefined;
beforeEach(async () => {
  vi.clearAllMocks();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: true,
      json: async () => (url.includes("/en/") ? en : zh),
    })),
  );
  await setLocale("zh");
});
afterEach(() => {
  wrapper?.unmount();
  vi.unstubAllGlobals();
});
describe("teacher learning analysis", () => {
  it("does not invent mastery or show an empty result on transport failure", async () => {
    api.get.mockRejectedValueOnce(new Error("读取中断"));
    wrapper = mount(TeacherLearningAnalysis, {
      props: { courseId: "course-a" },
    });
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toBe("读取中断");
    expect(wrapper.find(".analysis-summary").exists()).toBe(false);
    expect(wrapper.find(".analysis-empty").exists()).toBe(false);
    api.get.mockResolvedValueOnce({ data: { items: [] } });
    await wrapper.get(".analysis-heading button").trigger("click");
    await flushPromises();
    expect(wrapper.find(".analysis-empty").exists()).toBe(true);
    expect(api.get.mock.calls[1]?.[0]).toBe(
      "/api/teacher/courses/course-a/exchange/feedback",
    );
    expect(api.get.mock.calls[1]?.[1]).toMatchObject({
      identityScope: "teacher",
    });
  });
  it("shows received attempt evidence without labeling it as knowledge mastery", async () => {
    api.get.mockResolvedValue({
      data: {
        items: [
          {
            feedback_id: "a",
            actor_id: "learner-a",
            kind: "practice_result",
            received_at: "2026-10-20T00:00:00+08:00",
            release_id: "r1",
            payload: {},
            assessment: {
              result: { passed: false },
              answer_payload: { selected_option_id: "A" },
              task: { prompt: "向量的定义是什么？" },
            },
          },
          {
            feedback_id: "b",
            actor_id: "learner-a",
            kind: "course_question",
            received_at: "2026-10-20T00:01:00+08:00",
            release_id: "r1",
            payload: { text: "请解释适用条件" },
          },
        ],
      },
    });
    wrapper = mount(TeacherLearningAnalysis, {
      props: { courseId: "course-a" },
    });
    await flushPromises();
    expect(wrapper.findAll("dd").map((node) => node.text())).toEqual([
      "1",
      "1",
      "1",
    ]);
    expect(wrapper.text()).toContain("本次作答需要再练");
    expect(wrapper.text()).not.toMatch(/掌握率|\d+%/);
    await wrapper.findAll("select")[1]!.setValue("course_question");
    expect(wrapper.findAll(".analysis-list button")).toHaveLength(1);
    expect(wrapper.get(".analysis-evidence").text()).toContain(
      "请解释适用条件",
    );
    await wrapper.get(".analysis-evidence button").trigger("click");
    expect(wrapper.emitted("feedback")).toHaveLength(1);
  });
  it("does not show a late response from a different course", async () => {
    let finish: (value: unknown) => void = () => {};
    api.get.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    wrapper = mount(TeacherLearningAnalysis, {
      props: { courseId: "course-a" },
    });
    api.get.mockResolvedValueOnce({ data: { items: [] } });
    await wrapper.setProps({ courseId: "course-b" });
    await flushPromises();
    finish({
      data: { items: [{ feedback_id: "old", actor_id: "私人旧课程记录" }] },
    });
    await flushPromises();
    expect(wrapper.text()).not.toContain("私人旧课程记录");
    expect(wrapper.find(".analysis-empty").exists()).toBe(true);
  });
});
