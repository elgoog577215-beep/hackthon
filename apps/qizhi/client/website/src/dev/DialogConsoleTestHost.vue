<template>
  <DeleteConfirmModal
    v-model="showAlert"
    title="测试 Alert 弹窗"
    entity-kind="资源"
    entity-name="测试条目"
    body-text="这是 Alert（删除确认）弹窗的测试正文。"
    @cancel="onAlertCancel"
    @confirm="onAlertConfirm"
  />
  <ConfirmDialogModal
    v-model="showMessage"
    variant="info"
    title="测试 Message 弹窗"
    message="这是 Message（普通提示）弹窗的测试正文。"
    confirm-label="确认"
    @cancel="onMessageCancel"
    @confirm="onMessageConfirm"
  />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import DeleteConfirmModal from '../components/DeleteConfirmModal.vue'
import ConfirmDialogModal from '../components/ConfirmDialogModal.vue'

const showAlert = ref(false)
const showMessage = ref(false)

function openAlert() {
  showAlert.value = true
  console.info('[dialog-test] 已打开 Alert 弹窗')
}

function openMessage() {
  showMessage.value = true
  console.info('[dialog-test] 已打开 Message 弹窗')
}

function onAlertCancel() {
  console.info('[dialog-test] Alert：已取消')
}

function onAlertConfirm() {
  showAlert.value = false
  console.info('[dialog-test] Alert：已确认（测试）')
}

function onMessageCancel() {
  console.info('[dialog-test] Message：已取消')
}

function onMessageConfirm() {
  showMessage.value = false
  console.info('[dialog-test] Message：已确认（测试）')
}

defineExpose({
  openAlert,
  openMessage,
})
</script>
