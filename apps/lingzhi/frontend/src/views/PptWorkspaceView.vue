<template>
  <PptWorkspace ref="workspace" />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import PptWorkspace from '../components/PptWorkspace.vue'

const workspace = ref<InstanceType<typeof PptWorkspace> | null>(null)
onBeforeRouteLeave(() => workspace.value?.prepareToLeave() ?? true)
</script>
