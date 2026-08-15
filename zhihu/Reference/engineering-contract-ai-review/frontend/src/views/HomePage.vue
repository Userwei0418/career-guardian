<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useAuth } from "../composables/useAuth";
import { useIdentity } from "../composables/useIdentity";
import { knowledgeArticles } from "../data/knowledge";
import http from "../api/http";

const router = useRouter();
const { currentUser } = useAuth();
const { currentIdentity, identityConfig, isIdentitySet, identityOptions, setIdentity } = useIdentity();
const recentContracts = ref([]);
const stats = ref({ total: 0, reviewed: 0, archived: 0 });
const loading = ref(false);
const identityDialogVisible = ref(false);

const greeting = computed(() => {
  const hour = new Date().getHours();
  const name = currentUser.value?.username || "朋友";
  if (hour < 6) return `夜深了，${name} 🌙`;
  if (hour < 12) return `早上好，${name} ☀️`;
  if (hour < 14) return `中午好，${name} 🌤️`;
  if (hour < 18) return `下午好，${name} 🌈`;
  return `晚上好，${name} 🌙`;
});

const recommendedArticles = computed(() => {
  if (!identityConfig.value) return [];
  const slugs = identityConfig.value.recommendedSlugs || [];
  return slugs
    .map(slug => knowledgeArticles.find(a => a.slug === slug))
    .filter(Boolean)
    .slice(0, 4);
});

const identityTips = computed(() => {
  return identityConfig.value?.homeTips || [
    "签合同前看清薪资结构（底薪+绩效+补贴）",
    "五险一金是法定义务，不能放弃",
    "保留一份合同原件",
  ];
});

const stageGuide = computed(() => {
  const guides = {
    student: { title: "在校准备", steps: ["找第一段实习，积累简历素材", "了解实习协议和三方协议的区别", "学习基本劳动法知识", "用薪资计算器了解市场行情"] },
    intern: { title: "实习期", steps: ["确认实习协议条款是否合理", "保留工作记录和成果", "了解转正流程和条件", "为秋招/春招做准备"] },
    freshGrad: { title: "求职入职", steps: ["面试时问清薪资结构和五险一金", "拿到Offer后用AI审查合同", "算清到手工资和生活成本", "入职第一周完成Checklist"] },
    junior: { title: "职场起步", steps: ["核对第一笔工资条是否正确", "建立应急基金（3~6个月生活费）", "制定攒钱计划并开始执行", "了解专项附加扣除省个税"] },
    senior: { title: "稳定发展", steps: ["关注年终奖计税方式优化", "评估公积金买房/提取时机", "考虑长期理财和保险配置", "如需换城市，了解社保转移"] },
    experienced: { title: "看新机会", steps: ["评估跳槽的利弊和风险", "注意竞业限制和社保断缴", "用Offer对比器比较多个选择", "离职时提取公积金"] },
  };
  const code = currentIdentity.value;
  return guides[code] || guides.freshGrad;
});

const quickActions = computed(() => {
  const base = [
    { icon: "💰", title: "薪资计算器", desc: "算算到手有多少", path: "/salary" },
    { icon: "📚", title: "知识学堂", desc: "学点劳动法，不踩坑", path: "/knowledge" },
  ];
  const identityActions = {
    student: [{ icon: "📤", title: "上传合同", desc: "实习协议也帮你看看", path: "/contracts/upload" }],
    intern: [{ icon: "📤", title: "上传合同", desc: "帮你审查实习协议", path: "/contracts/upload" }],
    freshGrad: [{ icon: "📤", title: "上传合同", desc: "AI帮你找出隐患条款", path: "/contracts/upload" }],
    junior: [{ icon: "📤", title: "上传合同", desc: "续签/变更也帮你看看", path: "/contracts/upload" }],
    senior: [{ icon: "📤", title: "上传合同", desc: "帮你审查合同条款", path: "/contracts/upload" }],
    experienced: [{ icon: "📤", title: "上传合同", desc: "新Offer合同帮你审查", path: "/contracts/upload" }],
  };
  const extra = identityActions[currentIdentity.value] || identityActions.freshGrad;
  return [...extra, ...base];
});

const todayTip = computed(() => {
  const tips = identityTips.value;
  const dayIndex = new Date().getDate() % tips.length;
  return tips[dayIndex];
});

function openIdentityDialog() {
  identityDialogVisible.value = true;
}

function selectIdentity(code) {
  setIdentity(code);
  identityDialogVisible.value = false;
}

onMounted(async () => {
  if (!isIdentitySet.value) {
    identityDialogVisible.value = true;
  }
  loading.value = true;
  try {
    const { data } = await http.get("/contracts", { params: { include_archived: false } });
    recentContracts.value = data.slice(0, 5);
    stats.value.total = data.length;
    stats.value.reviewed = data.filter(c => c.review_status === "completed").length;
    stats.value.archived = data.filter(c => c.status === "archived").length;
  } catch {
    // silently handle
  } finally {
    loading.value = false;
  }
});

function riskTagType(level) {
  const levels = Array.isArray(level) ? level : [level];
  if (levels.includes("high")) return "danger";
  if (levels.includes("medium")) return "warning";
  return "success";
}

function riskTagLabel(level) {
  const levels = Array.isArray(level) ? level : [level];
  if (levels.includes("high")) return "高风险";
  if (levels.includes("medium")) return "中风险";
  if (levels.includes("low")) return "低风险";
  return "未审查";
}
</script>

<template>
  <div class="page-stack" v-loading="loading">
    <div class="welcome-banner">
      <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
        <div>
          <h2>{{ greeting }}</h2>
          <p>帮你读懂合同、算清薪资、规划未来。你的职场路上，职护陪你走。</p>
        </div>
        <el-button v-if="isIdentitySet" round size="small" style="background: rgba(255,255,255,0.2); color: #fff; border: 1px solid rgba(255,255,255,0.3);" @click="openIdentityDialog">
          {{ identityConfig?.icon }} {{ identityConfig?.label }} · 切换身份
        </el-button>
      </div>
    </div>

    <div class="identity-tip-card" v-if="isIdentitySet">
      <span class="identity-tip-icon">{{ identityConfig?.icon }}</span>
      <div>
        <strong>{{ identityConfig?.label }}专属提示</strong>
        <p>{{ identityConfig?.salaryTip }}</p>
      </div>
    </div>

    <div class="quick-actions">
      <el-card v-for="action in quickActions" :key="action.title" class="quick-action-card" shadow="hover" @click="router.push(action.path)">
        <div class="quick-action-icon">{{ action.icon }}</div>
        <div class="quick-action-title">{{ action.title }}</div>
        <div class="quick-action-desc">{{ action.desc }}</div>
      </el-card>
    </div>

    <div class="knowledge-preview" v-if="todayTip">
      <div class="kp-label">💡 今日小贴士</div>
      <div class="kp-title">{{ todayTip }}</div>
      <router-link to="/knowledge" class="kp-link">去知识学堂了解更多 →</router-link>
    </div>

    <el-card v-if="isIdentitySet && stageGuide">
      <template #header>
        <div class="card-header">
          <span>{{ identityConfig?.icon }} {{ stageGuide.title }} · 你现在可以做的</span>
        </div>
      </template>
      <div class="stage-steps">
        <div v-for="(step, idx) in stageGuide.steps" :key="idx" class="stage-step">
          <span class="stage-step-num">{{ idx + 1 }}</span>
          <span>{{ step }}</span>
        </div>
      </div>
    </el-card>

    <el-card v-if="recommendedArticles.length">
      <template #header>
        <div class="card-header">
          <span>{{ identityConfig?.icon }} 为你推荐的知识点</span>
          <el-button text type="primary" @click="router.push('/knowledge')">查看全部</el-button>
        </div>
      </template>
      <div class="recommended-grid">
        <el-card
          v-for="article in recommendedArticles"
          :key="article.slug"
          class="recommended-item"
          shadow="hover"
          @click="router.push('/knowledge')"
        >
          <el-tag size="small" type="info">{{ article.tag }}</el-tag>
          <h4>{{ article.title }}</h4>
          <p>{{ article.summary }}</p>
        </el-card>
      </div>
    </el-card>

    <el-card v-if="recentContracts.length">
      <template #header>
        <div class="card-header">
          <span>最近审查</span>
          <el-button text type="primary" @click="router.push('/contracts')">查看全部</el-button>
        </div>
      </template>
      <el-table :data="recentContracts" size="small" stripe>
        <el-table-column prop="original_filename" label="文件名" min-width="200" />
        <el-table-column prop="contract_name" label="合同名称" min-width="180">
          <template #default="{ row }">{{ row.contract_name || "-" }}</template>
        </el-table-column>
        <el-table-column label="风险" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.risk_levels?.length" size="small" :type="riskTagType(row.risk_levels)">
              {{ riskTagLabel(row.risk_levels) }}
            </el-tag>
            <span v-else style="color: var(--text-tertiary)">-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.review_status === 'completed' ? 'success' : 'info'">
              {{ row.review_status === "completed" ? "已审查" : "待审查" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="router.push(`/contracts/${row.file_id}`)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-else-if="!loading">
      <el-empty description="还没有合同哦，上传你的第一份合同试试？">
        <el-button type="primary" @click="router.push('/contracts/upload')">去上传</el-button>
      </el-empty>
    </el-card>

    <el-dialog v-model="identityDialogVisible" title="选择你的身份" width="580px" :close-on-click-modal="false">
      <p style="color: var(--text-secondary); margin-bottom: 20px;">不同身份会看到不同的推荐内容和提示，随时可以切换。</p>
      <div class="identity-options">
        <div
          v-for="(opt, code) in identityOptions"
          :key="code"
          class="identity-option"
          :class="{ active: currentIdentity === code }"
          @click="selectIdentity(code)"
        >
          <div class="identity-option-icon">{{ opt.icon }}</div>
          <div class="identity-option-info">
            <strong>{{ opt.label }}</strong>
            <p>{{ opt.description }}</p>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.identity-tip-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 18px;
  background: var(--color-primary-50);
  border: 1px solid var(--color-primary-200);
  border-radius: var(--radius-lg);
}
.identity-tip-icon { font-size: 24px; flex-shrink: 0; margin-top: 2px; }
.identity-tip-card strong { display: block; font-size: 14px; color: var(--text-primary); margin-bottom: 2px; }
.identity-tip-card p { margin: 0; font-size: 13px; color: var(--text-secondary); line-height: 1.5; }

.recommended-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
.recommended-item { cursor: pointer; transition: all var(--transition-base); }
.recommended-item:hover { transform: translateY(-2px); }
.recommended-item h4 { margin: 8px 0 4px; font-size: 14px; font-weight: 600; }
.recommended-item p { margin: 0; font-size: 13px; color: var(--text-secondary); }

.identity-options { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.identity-option {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 16px; border: 2px solid var(--border-color);
  border-radius: var(--radius-lg); cursor: pointer;
  transition: all var(--transition-base);
}
.identity-option:hover { border-color: var(--color-primary-300); background: var(--bg-hover); }
.identity-option.active { border-color: var(--color-primary-500); background: var(--color-primary-50); }
.identity-option-icon { font-size: 32px; flex-shrink: 0; }
.identity-option-info strong { font-size: 16px; color: var(--text-primary); }
.identity-option-info p { margin: 4px 0 0; font-size: 13px; color: var(--text-secondary); }

.stage-steps { display: flex; flex-direction: column; gap: 10px; }
.stage-step { display: flex; align-items: center; gap: 12px; font-size: 14px; color: var(--text-secondary); padding: 8px 12px; background: var(--color-gray-50); border-radius: var(--radius-md); }
.stage-step-num { width: 24px; height: 24px; border-radius: 50%; background: var(--color-primary-500); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; flex-shrink: 0; }
</style>
