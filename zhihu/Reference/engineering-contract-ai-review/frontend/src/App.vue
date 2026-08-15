<script setup>
import { computed, onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { HomeFilled, Document, Files, FolderOpened, Lock, Setting, Upload, User, Reading, Collection, Coin, TrendCharts, DataAnalysis } from "@element-plus/icons-vue";

import { useAuth } from "./composables/useAuth";
import { roleLabel } from "./utils/labels";

const route = useRoute();
const router = useRouter();

const { currentUser, isAuthenticated, isAdmin, hasAnyRole, syncAuthState } = useAuth();

const mainMenuItems = [
  { index: "/", label: "首页", icon: HomeFilled },
  { index: "/contracts", label: "我的合同", icon: Files },
  { index: "/contracts/upload", label: "上传合同", icon: Upload },
  { index: "/salary", label: "薪资与理财", icon: Coin },
  { index: "/offer-compare", label: "Offer对比", icon: DataAnalysis },
  { index: "/knowledge", label: "知识学堂", icon: Reading },
];

const adminMenuItems = [
  { index: "/admin/rules", label: "规则管理", icon: Setting, roles: ["admin"] },
  { index: "/admin/users", label: "用户管理", icon: User, roles: ["admin"] },
  { index: "/admin/settings", label: "系统设置", icon: Setting, roles: ["admin"] },
  { index: "/admin/logs", label: "操作日志", icon: Collection, roles: ["admin"] },
];

const visibleAdminItems = computed(() =>
  adminMenuItems.filter((item) => !item.roles || item.roles.some((role) => hasAnyRole(role)))
);

const userInitial = computed(() => {
  if (!currentUser.value) return "U";
  return currentUser.value.username.charAt(0).toUpperCase();
});

function handleSelect(index) {
  router.push(index);
}

function logout() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("current_user");
  router.push("/login");
  syncAuthState();
}

watch(
  () => route.fullPath,
  () => { syncAuthState(); },
  { immediate: true }
);

onMounted(() => { syncAuthState(); });
</script>

<template>
  <router-view v-if="route.path === '/login'" />

  <el-container v-else class="app-shell">
    <el-aside :width="'240px'" class="app-sidebar">
      <div class="brand">
        <div class="brand-icon">
          <el-icon><Document /></el-icon>
        </div>
        <div class="brand-text">
          <span class="title">职护</span>
          <span class="subtitle">你的职场全方位保障</span>
        </div>
      </div>

      <el-menu :default-active="route.path" class="nav-menu" @select="handleSelect">
        <el-menu-item
          v-for="item in mainMenuItems"
          :key="item.index"
          :index="item.index"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>

        <template v-if="visibleAdminItems.length">
          <div style="padding: 12px 12px 4px; font-size: 12px; color: var(--text-tertiary); font-weight: 500;">管理</div>
          <el-menu-item
            v-for="item in visibleAdminItems"
            :key="item.index"
            :index="item.index"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </el-menu-item>
        </template>
      </el-menu>

      <div v-if="isAuthenticated" class="sidebar-user">
        <span class="user-avatar">{{ userInitial }}</span>
        <span class="user-name">{{ currentUser?.username }}</span>
        <el-button text size="small" @click="logout" title="退出登录">
          <el-icon><Lock /></el-icon>
        </el-button>
      </div>
    </el-aside>

    <el-container>
      <el-header class="app-header">
        <div class="header-title">
          <h1>{{ route.meta.title || "职护" }}</h1>
        </div>
        <div class="header-actions">
          <span v-if="isAuthenticated" class="user-info">
            <span class="user-avatar">{{ userInitial }}</span>
            <span>{{ currentUser?.username }}</span>
          </span>
        </div>
      </el-header>

      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>
