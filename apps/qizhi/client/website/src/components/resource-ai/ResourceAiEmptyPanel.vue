<template>
  <div class="rai-empty">
    <div class="rai-empty__float rai-empty__float--1" aria-hidden="true" />
    <div class="rai-empty__float rai-empty__float--2 delay-1" aria-hidden="true" />
    <div class="rai-empty__float rai-empty__float--3 delay-2" aria-hidden="true" />

    <div class="rai-empty__panel">
      <span class="material-symbols-outlined rai-empty__sparkle-bg" aria-hidden="true">{{ sparkleIcon }}</span>

      <div class="rai-empty__icon-wrap">
        <span class="material-symbols-outlined rai-empty__main-icon" aria-hidden="true">{{ icon }}</span>
      </div>

      <h3 class="rai-empty__title">{{ title }}</h3>
      <p class="rai-empty__desc">{{ description }}</p>

      <p v-if="guideText" class="rai-empty__guide" aria-hidden="true">
        <span class="rai-empty__guide-text">{{ guideText }}</span>
        <span class="material-symbols-outlined rai-empty__guide-arrow" aria-hidden="true">arrow_forward</span>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string
    description: string
    guideText?: string
    icon?: string
    sparkleIcon?: string
  }>(),
  {
    guideText: '请在右侧输入框中开始输入',
    icon: 'edit_document',
    sparkleIcon: 'auto_awesome',
  },
)
</script>

<style scoped>
.rai-empty {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 24px;
  overflow: hidden;
}

.rai-empty__float {
  position: absolute;
  border-radius: 16px;
  opacity: 0.45;
  pointer-events: none;
  animation: rai-float 6s ease-in-out infinite;
}

.rai-empty__float--1 {
  width: 120px;
  height: 120px;
  top: 12%;
  left: 8%;
  background: linear-gradient(135deg, #dfe0ff 0%, #bdc2ff 100%);
}

.rai-empty__float--2 {
  width: 80px;
  height: 80px;
  bottom: 18%;
  right: 12%;
  background: linear-gradient(135deg, #e2dfff 0%, #c2c1ff 100%);
}

.rai-empty__float--3 {
  width: 56px;
  height: 56px;
  top: 55%;
  left: 18%;
  background: #efedee;
}

.delay-1 {
  animation-delay: 1s;
}
.delay-2 {
  animation-delay: 2s;
}

@keyframes rai-float {
  0% {
    transform: translateY(0) rotate(0deg);
  }
  50% {
    transform: translateY(-15px) rotate(2deg);
  }
  100% {
    transform: translateY(0) rotate(0deg);
  }
}

.rai-empty__panel {
  position: relative;
  z-index: 1;
  max-width: 480px;
  min-height: 320px;
  width: 100%;
  padding: 52px 44px 48px;
  border-radius: 16px;
  text-align: center;
  overflow: hidden;
  background: transparent;
}

.rai-empty__sparkle-bg {
  position: absolute;
  top: 36px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 152px;
  line-height: 1;
  color: #9ca3af;
  opacity: 0.07;
  font-variation-settings: 'FILL' 1;
  pointer-events: none;
  user-select: none;
  z-index: 0;
}

.rai-empty__icon-wrap {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  margin: 0 auto 28px;
  border-radius: 50%;
  background: rgba(68, 80, 183, 0.1);
}

.rai-empty__main-icon {
  font-size: 36px;
  color: #4450b7;
}

.rai-empty__title {
  position: relative;
  z-index: 1;
  margin: 0 0 20px;
  font-size: 26px;
  font-weight: 300;
  letter-spacing: -0.3px;
  color: #08090a;
  line-height: 1.3;
}

.rai-empty__desc {
  position: relative;
  z-index: 1;
  margin: 0 0 28px;
  font-size: 14px;
  line-height: 1.65;
  color: #4a4d53;
}

.rai-empty__guide {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 8px 0 0;
  padding: 0;
  font-size: 14px;
  font-weight: 500;
  pointer-events: none;
  user-select: none;
}

.rai-empty__guide-text {
  color: #4a4d53;
}

.rai-empty__guide-arrow {
  font-size: 18px !important;
  color: #bdc2ff;
}
</style>
