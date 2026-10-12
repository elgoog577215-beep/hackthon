import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
vi.mock("mermaid", () => ({ default: { initialize: vi.fn(), run: vi.fn() } }));
import MarkdownRenderer from "../../components/MarkdownRenderer.vue";
import { teachingDiagramSamples } from "../../../dev/teaching-diagram-samples";

const payload = JSON.stringify(
  teachingDiagramSamples.find((s) => s.type === "flowchart"),
);
const block = "```lingzhi-diagram\n" + payload + "\n```";
async function settle() {
  await flushPromises();
  await new Promise((resolve) => requestAnimationFrame(resolve));
  await nextTick();
  await flushPromises();
}

describe("shared handout and AI diagram integration", () => {
  it("renders multiple diagrams with distinct SVG identities, captions and full data", async () => {
    const wrapper = mount(MarkdownRenderer, {
      props: {
        content: `Before\n\n${block}\n\nBetween\n\n${block}\n\nAfter`,
        enableCodeRun: false,
      },
    });
    await settle();
    expect(wrapper.findAll("figure.teaching-diagram")).toHaveLength(2);
    expect(wrapper.findAll('svg[role="img"]')).toHaveLength(2);
    const ids = wrapper.findAll("[id]").map((el) => el.attributes("id"));
    expect(new Set(ids).size).toBe(ids.length);
    expect(wrapper.text()).toContain("Before");
    expect(wrapper.text()).toContain("After");
    expect(wrapper.find("figcaption").text()).toContain("手写教学示例");
    expect(wrapper.find(".diagram-data").text()).toContain("范围");
    await wrapper.setProps({ searchWords: ["unmatched-search"] });
    await settle();
    expect(wrapper.findAll('svg[role="img"]')).toHaveLength(2);
    wrapper.unmount();
  });
  it("waits for a closed fence, then draws a streamed answer and clears on replacement", async () => {
    const wrapper = mount(MarkdownRenderer, {
      props: {
        content: "Before\n\n```lingzhi-diagram\n" + payload,
        enableCodeRun: false,
      },
    });
    await settle();
    expect(wrapper.find(".diagram-pending").exists()).toBe(true);
    expect(wrapper.find('svg[role="img"]').exists()).toBe(false);
    await wrapper.setProps({ content: `Before\n\n${block}` });
    await settle();
    expect(wrapper.find('svg[role="img"]').exists()).toBe(true);
    await wrapper.setProps({ content: "Different lesson" });
    await settle();
    expect(wrapper.find("figure").exists()).toBe(false);
    expect(wrapper.text()).toBe("Different lesson");
    wrapper.unmount();
  });
  it("preserves invalid data and a readable summary without executing markup", async () => {
    const wrapper = mount(MarkdownRenderer, {
      props: {
        content:
          "```lingzhi-diagram\n" +
          JSON.stringify({
            schema_version: "teaching_diagram_v1",
            type: "unknown",
            title: "<script>alert(1)</script>",
            summary: "Keep this explanation",
            source: "Example",
          }) +
          "\n```",
      },
    });
    await settle();
    expect(wrapper.find(".diagram-error").exists()).toBe(true);
    expect(wrapper.text()).toContain("Keep this explanation");
    expect(wrapper.find("script").exists()).toBe(false);
    expect(wrapper.find("pre").text()).toContain("unknown");
    wrapper.unmount();
  });
});
