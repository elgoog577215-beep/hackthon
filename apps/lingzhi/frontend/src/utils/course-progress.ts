/**
 * 生成进度上"现在在哪"的唯一取值口径。
 *
 * 后端推 `current_node_location.label`（形如「第2章第3节 · 不确定性原理」）。
 * 老师问的是进度走到整门课的什么位置，只报小节名答不了——课程里重名小节不少见。
 *
 * 位置缺失时退回小节名再退回 message：旧任务、导入任务和正文阶段之前的
 * 阶段都没有位置，这些情况不该让进度栏变空。
 */
export function taskProgressStep(
  source: { current_node_location?: { label?: string } | null; current_node_name?: string; message?: string } | null | undefined,
  fallback = '',
): string {
  if (!source) return fallback
  const label = String(source.current_node_location?.label || '').trim()
  if (label) return label
  const nodeName = String(source.current_node_name || '').trim()
  if (nodeName) return nodeName
  return String(source.message || '').trim() || fallback
}
