<template>
    <div :id="'node-' + node.node_id" 
         class="content-node-optimized scroll-mt-20 sm:scroll-mt-22 lg:scroll-mt-24 transition-all duration-500 animate-fade-in-up"
         :style="{ animationDelay: (index * 50) + 'ms' }">

        <!-- Level 1: Course Title / Part -->
        <div v-if="node.node_level === 1" class="relative overflow-hidden rounded-3xl sm:rounded-[2.5rem] bg-white/60 backdrop-blur-2xl border border-white/60 shadow-xl shadow-primary-500/5 mb-16 sm:mb-20 lg:mb-24 group hover:shadow-2xl hover:shadow-primary-500/10 transition-shadow duration-500">
            <!-- Background Decor -->
            <div class="absolute inset-0 bg-gradient-to-br from-white/60 via-transparent to-white/20 pointer-events-none"></div>
            <div class="absolute -top-[40%] -right-[20%] w-[80%] h-[120%] bg-gradient-to-b from-primary-100/40 to-transparent rounded-full blur-[100px] pointer-events-none opacity-60 mix-blend-multiply"></div>
            <div class="absolute -bottom-[40%] -left-[20%] w-[80%] h-[120%] bg-gradient-to-t from-pink-100/40 to-transparent rounded-full blur-[100px] pointer-events-none opacity-60 mix-blend-multiply"></div>

            <div class="relative z-10 p-8 sm:p-12 lg:p-16 xl:p-20 flex flex-col items-center text-center">
                <!-- Badge -->
                <div class="inline-flex items-center gap-2 px-3 sm:px-4 py-1 sm:py-1.5 rounded-full bg-white/80 border border-slate-200/60 shadow-sm backdrop-blur-md mb-6 sm:mb-8 lg:mb-10 group-hover:-translate-y-1 transition-transform duration-500">
                    <span class="relative flex h-2 w-2">
                    <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-400 opacity-75"></span>
                    <span class="relative inline-flex rounded-full h-2 w-2 bg-primary-500"></span>
                    </span>
                    <span class="text-[9px] sm:text-[10px] font-bold tracking-widest text-slate-500 uppercase font-sans">Interactive Course</span>
                </div>

                <!-- Title -->
                <h1 class="text-3xl sm:text-4xl md:text-5xl lg:text-6xl font-black text-slate-800 mb-6 sm:mb-7 lg:mb-8 tracking-tight drop-shadow-sm font-display leading-[1.15] max-w-4xl bg-clip-text text-transparent bg-gradient-to-br from-slate-900 via-slate-800 to-slate-700">
                    {{ node.node_name.replace(/《|》/g, '') }}
                </h1>

                <!-- Divider -->
                <div class="flex items-center gap-4 sm:gap-6 mb-6 sm:mb-8 lg:mb-10 opacity-40">
                    <div class="w-12 sm:w-16 h-px bg-gradient-to-r from-transparent via-slate-400 to-transparent"></div>
                    <div class="w-1.5 h-1.5 rounded-full bg-slate-400"></div>
                    <div class="w-12 sm:w-16 h-px bg-gradient-to-r from-transparent via-slate-400 to-transparent"></div>
                </div>

                <!-- Description -->
                <div class="prose prose-base sm:prose-lg prose-slate text-slate-600 max-w-2xl sm:max-w-3xl mx-auto font-sans leading-relaxed mix-blend-multiply text-center font-medium [&_pre]:text-left [&_blockquote]:text-left [&_ul]:text-left [&_ol]:text-left [&_table]:text-left">
                    <MarkdownRenderer :content="node.node_content" :search-words="searchWords" />
                </div>
            </div>
        </div>

        <!-- Level 2: Chapter -->
        <div v-else-if="node.node_level === 2" class="mt-12 sm:mt-14 lg:mt-16 mb-8 sm:mb-10 lg:mb-12 relative group">
            <!-- Decorative Background Elements -->
            <div class="absolute -inset-4 bg-gradient-to-br from-primary-50/50 via-white to-indigo-50/30 rounded-3xl blur-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-700 -z-10"></div>

            <div class="relative bg-white rounded-2xl sm:rounded-3xl overflow-hidden shadow-[0_4px_20px_-4px_rgba(0,0,0,0.1)] border border-slate-100 hover:shadow-[0_20px_50px_-12px_rgba(0,0,0,0.15)] transition-all duration-500">
                <!-- Top Accent Bar -->
                <div class="h-1.5 bg-gradient-to-r from-primary-400 via-indigo-500 to-purple-500"></div>

                <div class="p-6 sm:p-8 lg:p-10">
                    <!-- Top Row: Badge & Metadata -->
                    <div class="flex items-center justify-between flex-wrap gap-3 mb-6">
                        <div class="flex items-center gap-3">
                            <div class="flex items-center gap-2 px-3 py-1.5 bg-gradient-to-r from-slate-800 to-slate-700 text-white rounded-full shadow-md">
                                <el-icon :size="12" class="text-primary-300"><Reading /></el-icon>
                                <span class="text-[11px] font-bold tracking-wider uppercase">Chapter</span>
                            </div>
                            <span class="text-2xl font-black text-slate-200">{{ String(index + 1).padStart(2, '0') }}</span>
                        </div>

                        <!-- Metadata Pills -->
                        <div class="flex items-center gap-2">
                            <div v-if="node.is_read" class="flex items-center gap-1.5 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-3 py-1.5 rounded-full shadow-sm">
                                <el-icon :size="12"><Check /></el-icon> 已读
                            </div>
                        </div>
                    </div>

                    <!-- Middle Row: Title & Action -->
                    <div class="flex flex-col lg:flex-row lg:items-end justify-between gap-6">
                        <div class="flex-1">
                            <h2 class="text-3xl sm:text-4xl lg:text-5xl font-black text-slate-800 tracking-tight leading-[1.1] mb-4">
                                <span class="bg-clip-text text-transparent bg-gradient-to-br from-slate-900 via-slate-800 to-slate-600">
                                    {{ node.node_name }}
                                </span>
                            </h2>

                            <!-- Decorative Line -->
                            <div class="flex items-center gap-3 mb-4">
                                <div class="w-16 h-1 bg-gradient-to-r from-primary-500 to-indigo-500 rounded-full"></div>
                                <div class="w-2 h-2 rounded-full bg-primary-400"></div>
                                <div class="w-8 h-0.5 bg-slate-200 rounded-full"></div>
                            </div>
                        </div>

                        <div class="flex-shrink-0 mb-4 lg:mb-0">
                            <el-button 
                                type="primary" 
                                plain 
                                round 
                                class="!px-4 hover:!scale-105 transition-transform"
                                @click="$emit('start-quiz', node)">
                                <el-icon class="mr-1"><MagicStick /></el-icon> 题目测试
                            </el-button>
                        </div>
                    </div>

                    <!-- Bottom Row: Content -->
	                    <div v-if="node.node_content || displayBlocks.length" class="mt-8 pt-8 border-t border-slate-100">
	                        <div v-if="displayBlocks.length" class="space-y-4">
	                            <details
	                                v-for="block in displayBlocks"
	                                :key="block.block_id"
	                                class="border-t border-slate-100 first:border-t-0 py-4"
	                                :open="block.order < 2">
	                                <summary class="cursor-pointer list-none flex items-center justify-between gap-3 text-slate-800">
	                                    <div class="min-w-0">
	                                        <div class="text-xs font-semibold text-primary-500">{{ blockTypeLabel(block.type) }}</div>
	                                        <div class="font-bold truncate">{{ block.title }}</div>
	                                    </div>
	                                    <el-button text size="small" @click.stop.prevent="$emit('regenerate-block', node, block)">
	                                        <el-icon><RefreshRight /></el-icon>
	                                        <span>重写</span>
	                                    </el-button>
	                                </summary>
	                                <div class="prose prose-slate max-w-none prose-lg mt-4">
	                                    <MarkdownRenderer :content="block.content" :search-words="searchWords" />
	                                </div>
	                            </details>
	                        </div>
	                        <div v-else class="prose prose-slate max-w-none prose-lg">
	                            <MarkdownRenderer :content="node.node_content" :search-words="searchWords" />
	                        </div>
	                    </div>
                </div>
            </div>
        </div>

        <!-- Level 3+: Content Card -->
        <div v-else class="group relative pl-4 sm:pl-5 lg:pl-6 border-l-2 border-slate-200 hover:border-primary-300 transition-colors duration-300">
            <div class="absolute -left-[4.5px] sm:-left-[5px] top-1.5 w-2 sm:w-2.5 h-2 sm:h-2.5 rounded-full bg-slate-200 border border-white shadow-sm group-hover:bg-primary-400 group-hover:scale-125 transition-all duration-300"></div>

            <div class="flex items-center justify-between mb-2 sm:mb-3 group/header">
                <h3 class="text-base sm:text-lg font-semibold text-slate-700 flex items-center gap-2 pr-2">
                    {{ node.node_name }}
                </h3>
            </div>

            <div class="bg-white/60 backdrop-blur-sm p-3 sm:p-4 lg:p-5 xl:p-6 rounded-lg sm:rounded-xl relative overflow-hidden border border-slate-100/60 group-hover:bg-white/80 group-hover:border-slate-200/80 group-hover:shadow-sm transition-all duration-300">
                <div
                    class="prose prose-slate max-w-none content-render"
                    :style="{
                        '--content-font-size': fontSize + 'px',
                        '--content-line-height': String(lineHeight),
                        fontSize: fontSize + 'px',
                        fontFamily: fontFamily === 'mono' ? 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' : (fontFamily === 'serif' ? 'ui-serif, Georgia, Cambria, Times New Roman, Times, serif' : '-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica Neue, Arial, Noto Sans, sans-serif, Apple Color Emoji, Segoe UI Emoji, Segoe UI Symbol, Noto Color Emoji'),
                        lineHeight: lineHeight
                    }">
	                    <div v-if="displayBlocks.length" class="space-y-3">
	                        <details
	                            v-for="block in displayBlocks"
	                            :key="block.block_id"
	                            class="border-t border-slate-100 first:border-t-0 py-3"
	                            :open="block.order < 2">
	                            <summary class="cursor-pointer list-none flex items-center justify-between gap-3 text-slate-800">
	                                <div class="min-w-0">
	                                    <div class="text-xs font-semibold text-primary-500">{{ blockTypeLabel(block.type) }}</div>
	                                    <div class="font-bold truncate">{{ block.title }}</div>
	                                </div>
	                                <el-button text size="small" @click.stop.prevent="$emit('regenerate-block', node, block)">
	                                    <el-icon><RefreshRight /></el-icon>
	                                    <span>重写</span>
	                                </el-button>
	                            </summary>
	                            <div class="mt-3">
	                                <MarkdownRenderer :content="block.content" :search-words="searchWords" />
	                            </div>
	                        </details>
	                    </div>
	                    <MarkdownRenderer v-else :content="node.node_content" :search-words="searchWords" />
                    <!-- Streaming cursor indicator -->
                    <span v-if="isStreaming" class="inline-block w-0.5 h-5 bg-primary-500 animate-blink ml-0.5 align-text-bottom"></span>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import MarkdownRenderer from './MarkdownRenderer.vue';
import { MagicStick, Reading, Check, RefreshRight } from '@element-plus/icons-vue';
import type { ContentBlock } from '../stores/types';

const props = defineProps<{
  node: any;
  index: number;
  fontSize: number;
  fontFamily: string;
  lineHeight: number;
  searchWords?: string[];
  isStreaming?: boolean;
}>();

defineEmits<{
  (e: 'start-quiz', node: any): void;
  (e: 'regenerate-block', node: any, block: ContentBlock): void;
}>();

const typeLabels: Record<string, string> = {
  intro: '引入',
  concept: '概念',
  reasoning: '推理',
  example: '例子',
  application: '应用',
  exercise: '练习',
  summary: '小结',
  custom: '正文',
};

const blockTypeFromTitle = (title: string, order: number) => {
  const text = title.toLowerCase();
  const pairs: Array<[ContentBlock['type'], string[]]> = [
    ['intro', ['引入', '问题', '直观', '背景']],
    ['concept', ['概念', '定义', '核心', '基础']],
    ['reasoning', ['推理', '证明', '原理', '过程']],
    ['example', ['例子', '案例', '示例']],
    ['application', ['应用', '场景', '实践']],
    ['exercise', ['练习', '自测', '题']],
    ['summary', ['小结', '总结', '回顾']],
  ];
  for (const [type, keywords] of pairs) {
    if (keywords.some(keyword => text.includes(keyword))) return type;
  }
  return (['intro', 'concept', 'reasoning', 'example', 'application', 'exercise', 'summary'][order] || 'custom') as ContentBlock['type'];
};

const makeBlockId = (nodeId: string, order: number, type: string) => {
  const safeType = type.toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '') || 'block';
  return `${nodeId}-${order + 1}-${safeType}`;
};

const summarize = (content: string) => content.replace(/```[\s\S]*?```/g, ' ').replace(/[#>*_`$\\-]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 120);

const blocksFromMarkdown = (nodeId: string, markdown: string): ContentBlock[] => {
  const text = (markdown || '').trim();
  if (!text) return [];
  const headingRe = /^(#{2,4})\s+(.+?)\s*$/gm;
  const matches = Array.from(text.matchAll(headingRe));
  const parts: Array<[string, string]> = [];
  if (!matches.length) {
    parts.push(['正文', text]);
  } else {
    const first = matches[0];
    if (!first) return [];
    const firstIndex = first.index ?? 0;
    const preface = text.slice(0, firstIndex).trim();
    if (preface) parts.push(['引入问题', preface]);
    matches.forEach((match, idx) => {
      const start = (match.index ?? 0) + match[0].length;
      const next = matches[idx + 1];
      const end = next ? (next.index ?? text.length) : text.length;
      parts.push([(match[2] || '正文').trim(), text.slice(start, end).trim()]);
    });
  }
  return parts.map(([title, content], order) => {
    const type = blockTypeFromTitle(title, order);
    return {
      block_id: makeBlockId(nodeId, order, type),
      parent_block_id: null,
      type,
      title,
      content,
      summary: summarize(content),
      order,
      status: 'final',
    };
  });
};

const displayBlocks = computed<ContentBlock[]>(() => {
  const blocks = props.node?.content_blocks;
  if (Array.isArray(blocks) && blocks.length > 0) {
    return [...blocks].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  }
  return blocksFromMarkdown(props.node?.node_id || 'node', props.node?.node_content || '');
});

const blockTypeLabel = (type: string) => typeLabels[type] || '正文';
</script>

<style scoped>
/* Performance Optimization: lazy rendering handles this via renderedCount */
.content-node-optimized {
  /* content-visibility removed — it caused inaccurate scroll positions
     because off-screen nodes used estimated 500px heights instead of real ones.
     The renderedCount-based lazy rendering already limits DOM node count. */
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
.animate-blink {
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
.animate-blink {
  animation: blink 1s step-end infinite;
}
</style>
