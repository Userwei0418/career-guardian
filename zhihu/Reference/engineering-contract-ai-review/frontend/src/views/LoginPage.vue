<script setup>
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";

import http from "../api/http";

const router = useRouter();
const loading = ref(false);
const form = reactive({
  username: "admin",
  password: "Admin123456",
});

async function handleLogin() {
  loading.value = true;
  try {
    const { data } = await http.post("/auth/login", form);
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("current_user", JSON.stringify(data.user));
    ElMessage.success("欢迎回来！");
    router.push("/");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "登录失败，请检查用户名和密码");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card">
      <template #header>
        <div>
          <div class="login-header-icon">
            <el-icon><span style="font-size: 32px;">🛡️</span></el-icon>
          </div>
          <h2>嗨，欢迎来到职护 👋</h2>
          <p class="subtitle">帮你读懂合同，算清薪资，规划未来</p>
        </div>
      </template>

      <el-form label-position="top" @submit.prevent="handleLogin">
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" size="large" />
        </el-form-item>

        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            show-password
            size="large"
          />
        </el-form-item>

        <el-button type="primary" :loading="loading" class="full-width" size="large" @click="handleLogin">
          开始使用
        </el-button>
      </el-form>

      <div class="login-meta">
        <span>职护 · 你的职场全方位保障</span>
      </div>
    </el-card>
  </div>
</template>
