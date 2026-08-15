import { createRouter, createWebHistory } from "vue-router";

import HomePage from "../views/HomePage.vue";
import ContractDetailPage from "../views/ContractDetailPage.vue";
import ContractListPage from "../views/ContractListPage.vue";
import ContractUploadPage from "../views/ContractUploadPage.vue";
import KnowledgePage from "../views/KnowledgePage.vue";
import SalaryCalculatorPage from "../views/SalaryCalculatorPage.vue";
import OfferComparePage from "../views/OfferComparePage.vue";
import LoginPage from "../views/LoginPage.vue";
import ReviewLogPage from "../views/admin/ReviewLogPage.vue";
import RuleManagementPage from "../views/admin/RuleManagementPage.vue";
import SystemSettingsPage from "../views/admin/SystemSettingsPage.vue";
import UserManagementPage from "../views/admin/UserManagementPage.vue";

function getCurrentUser() {
  try {
    return JSON.parse(localStorage.getItem("current_user") || "null");
  } catch {
    return null;
  }
}

const routes = [
  {
    path: "/",
    component: HomePage,
    meta: { title: "首页", requiresAuth: true },
  },
  {
    path: "/login",
    component: LoginPage,
    meta: { title: "登录" },
  },
  {
    path: "/contracts",
    component: ContractListPage,
    meta: { title: "我的合同", requiresAuth: true },
  },
  {
    path: "/contracts/archived",
    component: ContractListPage,
    meta: { title: "归档合同", requiresAuth: true },
  },
  {
    path: "/contracts/upload",
    component: ContractUploadPage,
    meta: { title: "上传合同", requiresAuth: true, roles: ["admin", "reviewer"] },
  },
  {
    path: "/contracts/:id",
    component: ContractDetailPage,
    meta: { title: "合同体检报告", requiresAuth: true },
  },
  {
    path: "/knowledge",
    component: KnowledgePage,
    meta: { title: "知识学堂", requiresAuth: true },
  },
  {
    path: "/salary",
    component: SalaryCalculatorPage,
    meta: { title: "薪资与财务规划", requiresAuth: true },
  },
  {
    path: "/offer-compare",
    component: OfferComparePage,
    meta: { title: "Offer对比器", requiresAuth: true },
  },
  {
    path: "/finance",
    redirect: "/salary",
  },
  {
    path: "/admin/settings",
    component: SystemSettingsPage,
    meta: { title: "系统设置", requiresAuth: true, roles: ["admin"] },
  },
  {
    path: "/admin/users",
    component: UserManagementPage,
    meta: { title: "用户管理", requiresAuth: true, roles: ["admin"] },
  },
  {
    path: "/admin/rules",
    component: RuleManagementPage,
    meta: { title: "规则管理", requiresAuth: true, roles: ["admin"] },
  },
  {
    path: "/admin/logs",
    component: ReviewLogPage,
    meta: { title: "操作日志", requiresAuth: true, roles: ["admin"] },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  const isAuthenticated = Boolean(localStorage.getItem("access_token"));
  const currentUser = getCurrentUser();
  const roleSet = new Set(currentUser?.roles || []);
  if (to.meta.requiresAuth && !isAuthenticated) {
    return "/login";
  }
  if (to.path === "/login" && isAuthenticated) {
    return "/";
  }
  if (to.meta.roles?.length) {
    const hasAccess = to.meta.roles.some((role) => roleSet.has(role));
    if (!hasAccess) {
      return "/";
    }
  }
  return true;
});

export default router;
