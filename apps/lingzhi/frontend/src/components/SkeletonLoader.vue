<template>
  <div class="skeleton-container">
    <!-- Course Card Skeleton -->
    <div v-if="type === 'course-card'" class="skeleton-course-card">
      <div class="skeleton-course-icon"></div>
      <div class="skeleton-course-content">
        <div class="skeleton-title"></div>
        <div class="skeleton-meta">
          <div class="skeleton-chapters"></div>
          <div class="skeleton-progress"></div>
        </div>
      </div>
    </div>

    <!-- Tree Node Skeleton -->
    <div v-else-if="type === 'tree-node'" class="skeleton-tree-node">
      <div class="skeleton-node-header">
        <div class="skeleton-expand-icon"></div>
        <div class="skeleton-node-icon"></div>
        <div class="skeleton-node-title"></div>
      </div>
      <div v-if="hasChildren" class="skeleton-node-children">
        <SkeletonLoader type="tree-node" :has-children="false" v-for="i in 3" :key="i" />
      </div>
    </div>

    <!-- Content Skeleton -->
    <div v-else-if="type === 'content'" class="skeleton-content">
      <div class="skeleton-content-header">
        <div class="skeleton-title-lg"></div>
        <div class="skeleton-actions">
          <div class="skeleton-action-btn"></div>
          <div class="skeleton-action-btn"></div>
        </div>
      </div>
      <div class="skeleton-content-body">
        <div class="skeleton-paragraph"></div>
        <div class="skeleton-paragraph"></div>
        <div class="skeleton-paragraph short"></div>
        <div class="skeleton-code-block"></div>
        <div class="skeleton-paragraph"></div>
      </div>
    </div>

    <!-- Chat Message Skeleton -->
    <div v-else-if="type === 'chat'" class="skeleton-chat">
      <div class="skeleton-chat-avatar"></div>
      <div class="skeleton-chat-content">
        <div class="skeleton-chat-line"></div>
        <div class="skeleton-chat-line"></div>
        <div class="skeleton-chat-line short"></div>
      </div>
    </div>

    <!-- List Skeleton -->
    <div v-else-if="type === 'list'" class="skeleton-list">
      <div class="skeleton-list-item" v-for="i in count" :key="i">
        <div class="skeleton-list-icon"></div>
        <div class="skeleton-list-content">
          <div class="skeleton-list-title"></div>
          <div class="skeleton-list-desc"></div>
        </div>
      </div>
    </div>

    <!-- Default Skeleton -->
    <div v-else class="skeleton-default">
      <div class="skeleton-line"></div>
      <div class="skeleton-line"></div>
      <div class="skeleton-line short"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  type?: 'course-card' | 'tree-node' | 'content' | 'chat' | 'list' | 'default'
  hasChildren?: boolean
  count?: number
}>()
</script>

<style scoped>
.skeleton-container {
  width: 100%;
}

/* Shimmer Animation */
@keyframes shimmer {
  0% {
    background-position: -200% 0;
  }
  100% {
    background-position: 200% 0;
  }
}

.skeleton-shimmer {
  background: linear-gradient(
    90deg,
    #f1f5f9 25%,
    #e2e8f0 50%,
    #f1f5f9 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
}

/* Course Card Skeleton */
.skeleton-course-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: white;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
}

.skeleton-course-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  @extend .skeleton-shimmer;
}

.skeleton-course-content {
  flex: 1;
}

.skeleton-title {
  width: 60%;
  height: 20px;
  margin-bottom: 12px;
  @extend .skeleton-shimmer;
}

.skeleton-meta {
  display: flex;
  gap: 16px;
}

.skeleton-chapters,
.skeleton-progress {
  height: 14px;
  @extend .skeleton-shimmer;
}

.skeleton-chapters {
  width: 80px;
}

.skeleton-progress {
  width: 60px;
}

/* Tree Node Skeleton */
.skeleton-tree-node {
  padding: 8px 0;
}

.skeleton-node-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
}

.skeleton-expand-icon {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  @extend .skeleton-shimmer;
}

.skeleton-node-icon {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  @extend .skeleton-shimmer;
}

.skeleton-node-title {
  flex: 1;
  height: 16px;
  @extend .skeleton-shimmer;
}

.skeleton-node-children {
  margin-left: 24px;
  margin-top: 4px;
}

/* Content Skeleton */
.skeleton-content {
  padding: 24px;
}

.skeleton-content-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.skeleton-title-lg {
  width: 40%;
  height: 28px;
  @extend .skeleton-shimmer;
}

.skeleton-actions {
  display: flex;
  gap: 8px;
}

.skeleton-action-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  @extend .skeleton-shimmer;
}

.skeleton-content-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.skeleton-paragraph {
  height: 16px;
  @extend .skeleton-shimmer;
}

.skeleton-paragraph.short {
  width: 60%;
}

.skeleton-code-block {
  height: 100px;
  border-radius: 8px;
  @extend .skeleton-shimmer;
}

/* Chat Skeleton */
.skeleton-chat {
  display: flex;
  gap: 12px;
  padding: 16px;
}

.skeleton-chat-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  @extend .skeleton-shimmer;
}

.skeleton-chat-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skeleton-chat-line {
  height: 14px;
  @extend .skeleton-shimmer;
}

.skeleton-chat-line.short {
  width: 50%;
}

/* List Skeleton */
.skeleton-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.skeleton-list-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: white;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.skeleton-list-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  @extend .skeleton-shimmer;
}

.skeleton-list-content {
  flex: 1;
}

.skeleton-list-title {
  width: 70%;
  height: 16px;
  margin-bottom: 8px;
  @extend .skeleton-shimmer;
}

.skeleton-list-desc {
  width: 90%;
  height: 12px;
  @extend .skeleton-shimmer;
}

/* Default Skeleton */
.skeleton-default {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skeleton-line {
  height: 16px;
  @extend .skeleton-shimmer;
}

.skeleton-line.short {
  width: 60%;
}
</style>
