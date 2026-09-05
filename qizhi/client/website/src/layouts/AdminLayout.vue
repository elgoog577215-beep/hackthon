<template>
  <div class="admin-layout">
    <aside class="admin-sidebar" aria-label="运营后台导航">
      <div class="admin-sidebar-title">
        <div class="admin-sidebar-eyebrow">OPERATIONS</div>
        <div class="admin-sidebar-heading">运营后台</div>
      </div>
      <nav class="admin-sidebar-nav">
        <router-link
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="admin-sidebar-link"
          active-class="active"
        >
          <span class="admin-sidebar-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="20" height="20">
              <path :d="item.iconPath" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </span>
          <span class="admin-sidebar-text">{{ item.title }}</span>
        </router-link>
      </nav>
      <div class="admin-sidebar-footer">
        <div class="admin-user-name">{{ userStore.currentUser?.name || '管理员' }}</div>
        <div class="admin-user-id">{{ userStore.currentUser?.zju_id || '' }}</div>
      </div>
    </aside>
    <main class="admin-main route-slide-host">
      <RouteSlideView />
    </main>
  </div>
</template>

<script setup lang="ts">
import RouteSlideView from '../components/layout/RouteSlideView.vue'
import { useUserStore } from '../stores/user'

const userStore = useUserStore()

type NavItem = { to: string; title: string; iconPath: string }

const navItems: NavItem[] = [
  {
    to: '/admin/dashboard',
    title: '数据驾驶舱',
    iconPath: 'M3 12l9-9 9 9M5 10v10h14V10',
  },
  {
    to: '/admin/agents',
    title: '智能体管理',
    iconPath: 'M4 7h16M4 12h16M4 17h10M18 17h2',
  },
  {
    to: '/admin/users',
    title: '用户管理',
    iconPath: 'M16 11a4 4 0 1 0-8 0 4 4 0 0 0 8 0zM2 21a8 8 0 0 1 16 0M19 8v6M16 11h6',
  },
  {
    to: '/admin/feedbacks',
    title: '用户反馈',
    iconPath: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
  },
  {
    to: '/admin/audit-logs',
    title: '审计日志',
    iconPath: 'M9 3h6l5 5v13H4V3h5zM9 3v5h6M8 13h8M8 17h6',
  },
]
</script>

<style scoped>
.admin-layout {
  display: flex;
  min-height: calc(100vh - 64px);
  margin-top: 64px;
  background: #f5f7fb;
  box-sizing: border-box;
}

.admin-sidebar {
  width: 240px;
  flex-shrink: 0;
  background: #ffffff;
  border-right: 1px solid #e6eaf2;
  padding: 24px 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  box-sizing: border-box;
}

.admin-sidebar-title {
  padding: 0 8px 12px 8px;
  border-bottom: 1px solid #eef1f6;
}

.admin-sidebar-eyebrow {
  font-size: 12px;
  letter-spacing: 0.16em;
  color: #8a93a6;
  font-weight: 600;
  margin-bottom: 4px;
}

.admin-sidebar-heading {
  font-size: 20px;
  font-weight: 700;
  color: #1a2540;
  letter-spacing: 0.02em;
}

.admin-sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.admin-sidebar-link {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  color: #4b5670;
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  transition: background-color 0.18s ease, color 0.18s ease;
}

.admin-sidebar-link:hover {
  background: #f0f4fb;
  color: #1a2540;
}

.admin-sidebar-link.active {
  background: #e7eeff;
  color: #1f3c8b;
}

.admin-sidebar-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
}

.admin-sidebar-footer {
  margin-top: auto;
  padding: 12px 8px;
  border-top: 1px solid #eef1f6;
  color: #4b5670;
}

.admin-user-name {
  font-size: 14px;
  font-weight: 600;
  color: #1a2540;
}

.admin-user-id {
  font-size: 12px;
  color: #8a93a6;
  margin-top: 2px;
}

.admin-main {
  flex: 1;
  padding: 32px 36px;
  box-sizing: border-box;
  overflow-x: auto;
  --route-slide-bg: #f5f7fb;
}

@media (max-width: 960px) {
  .admin-layout {
    flex-direction: column;
  }
  .admin-sidebar {
    width: 100%;
    border-right: none;
    border-bottom: 1px solid #e6eaf2;
  }
  .admin-sidebar-nav {
    flex-direction: row;
    flex-wrap: wrap;
  }
  .admin-main {
    padding: 20px 16px;
  }
}
</style>
