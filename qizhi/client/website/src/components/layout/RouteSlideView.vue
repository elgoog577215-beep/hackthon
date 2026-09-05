<script setup lang="ts">
import { RouterView } from 'vue-router'
import { routeSlideTransitionName } from '../../lib/routeTransition'
</script>

<template>
  <RouterView v-slot="{ Component, route }">
    <!-- grid 叠层：进出两页同格并排滑，避免 out-in 中间空白 -->
    <div class="route-slide-stack">
      <Transition :name="routeSlideTransitionName">
        <component :is="Component" :key="route.fullPath" class="route-slide-page" />
      </Transition>
    </div>
  </RouterView>
</template>
