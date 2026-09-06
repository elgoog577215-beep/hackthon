<template>
  <div class="tp-empty">
    <div class="tp-empty__float tp-empty__float--1" aria-hidden="true" />
    <div class="tp-empty__float tp-empty__float--2 delay-1" aria-hidden="true" />
    <div class="tp-empty__float tp-empty__float--3 delay-2" aria-hidden="true" />

    <div class="tp-empty__panel">
      <span class="material-symbols-outlined tp-empty__sparkle-bg" aria-hidden="true">auto_awesome</span>

      <div class="tp-empty__icon-wrap">
        <span class="material-symbols-outlined tp-empty__doc-icon" aria-hidden="true">edit_document</span>
      </div>

      <h3 class="tp-empty__title">准备好生成教案</h3>
      <p class="tp-empty__desc">
        在右侧聊天框中输入您的要求，开始创建详细的教案。我们的 AI 将为您构建教学目标、活动设计等内容。
      </p>

      <p class="tp-empty__guide" aria-hidden="true">
        <span class="tp-empty__guide-text">请在右侧输入框中开始输入</span>
        <span class="material-symbols-outlined tp-empty__guide-arrow" aria-hidden="true">arrow_forward</span>
      </p>
    </div>
  </div>
</template>

<style scoped>
.tp-empty {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 24px;
  overflow: hidden;
}

.tp-empty__float {
  position: absolute;
  border-radius: 16px;
  opacity: 0.45;
  pointer-events: none;
  animation: tp-float 6s ease-in-out infinite;
}

.tp-empty__float--1 {
  width: 120px;
  height: 120px;
  top: 12%;
  left: 8%;
  background: linear-gradient(135deg, #dfe0ff 0%, #bdc2ff 100%);
}

.tp-empty__float--2 {
  width: 80px;
  height: 80px;
  bottom: 18%;
  right: 12%;
  background: linear-gradient(135deg, #e2dfff 0%, #c2c1ff 100%);
}

.tp-empty__float--3 {
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

@keyframes tp-float {
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

.tp-empty__panel {
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
  border: none;
  box-shadow: none;
}

.tp-empty__sparkle-bg {
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

.tp-empty__icon-wrap {
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

.tp-empty__doc-icon {
  font-size: 36px;
  color: #4450b7;
}

.tp-empty__title {
  position: relative;
  z-index: 1;
  margin: 0 0 20px;
  font-size: 26px;
  font-weight: 300;
  letter-spacing: -0.3px;
  color: #08090a;
  line-height: 1.3;
}

.tp-empty__desc {
  position: relative;
  z-index: 1;
  margin: 0 0 28px;
  font-size: 14px;
  line-height: 1.65;
  color: #4a4d53;
}

.tp-empty__guide {
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
  color: #8a8f98;
  pointer-events: none;
  user-select: none;
}

.tp-empty__guide .material-symbols-outlined {
  font-size: 20px;
  color: #a8adb6;
}

.tp-empty__guide-text {
  color: #4a4d53;
}

.tp-empty__guide-arrow {
  font-size: 18px !important;
  color: #bdc2ff;
}
</style>
