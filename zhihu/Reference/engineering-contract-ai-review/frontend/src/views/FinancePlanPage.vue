<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";

const STORAGE_KEY_COST = "life_cost_data";
const STORAGE_KEY_SALARY = "salary_calc_history";

const activeTab = ref("cost");

// ---- 生活成本 ----
const cityCostDefaults = {
  beijing:   { rent: 3000, food: 2500, transport: 400, utilities: 200, communication: 150, daily: 500, entertainment: 500 },
  shanghai:  { rent: 2800, food: 2500, transport: 400, utilities: 200, communication: 150, daily: 500, entertainment: 500 },
  guangzhou: { rent: 2000, food: 2000, transport: 300, utilities: 150, communication: 120, daily: 400, entertainment: 400 },
  shenzhen:  { rent: 2500, food: 2200, transport: 300, utilities: 180, communication: 130, daily: 450, entertainment: 450 },
  hangzhou:  { rent: 2200, food: 2200, transport: 350, utilities: 180, communication: 130, daily: 450, entertainment: 450 },
  chengdu:   { rent: 1500, food: 1800, transport: 250, utilities: 120, communication: 100, daily: 350, entertainment: 350 },
  wuhan:     { rent: 1400, food: 1600, transport: 200, utilities: 120, communication: 100, daily: 300, entertainment: 300 },
  nanjing:   { rent: 1800, food: 2000, transport: 300, utilities: 150, communication: 120, daily: 400, entertainment: 400 },
  xian:      { rent: 1300, food: 1500, transport: 200, utilities: 100, communication: 100, daily: 300, entertainment: 300 },
  changsha:  { rent: 1200, food: 1500, transport: 200, utilities: 100, communication: 100, daily: 300, entertainment: 300 },
  other:     { rent: 1500, food: 2000, transport: 300, utilities: 150, communication: 120, daily: 400, entertainment: 400 },
};

const costForm = reactive({
  city: "beijing",
  rent: 3000,
  utilities: 200,
  food: 2500,
  transport: 400,
  communication: 150,
  daily: 500,
  entertainment: 500,
  other: 0,
});

const totalCost = computed(() =>
  costForm.rent + costForm.utilities + costForm.food + costForm.transport +
  costForm.communication + costForm.daily + costForm.entertainment + costForm.other
);

const dailyCost = computed(() => Math.round(totalCost.value / 30));

function applyCityDefaults() {
  const defaults = cityCostDefaults[costForm.city] || cityCostDefaults.other;
  Object.assign(costForm, defaults);
}

watch(() => costForm.city, applyCityDefaults);

function saveCostData() {
  localStorage.setItem(STORAGE_KEY_COST, JSON.stringify({ ...costForm }));
  ElMessage.success("已保存");
}

// ---- 理财规划 ----
const salaryData = ref(null);
const goalAmount = ref(50000);
const goalType = ref("emergency");

const goalPresets = {
  emergency: { label: "应急基金（3~6个月生活费）", multiplier: 4.5 },
  house: { label: "买房首付", amount: 200000 },
  travel: { label: "旅行基金", amount: 20000 },
  custom: { label: "自定义目标", amount: 50000 },
};

const monthlySavings = computed(() => {
  if (!salaryData.value) return 0;
  return Math.max(0, salaryData.value.takeHome - totalCost.value);
});

const monthlyHousingFund = computed(() => {
  if (!salaryData.value) return 0;
  return salaryData.value.housingFund * 2 || 0;
});

const totalMonthlyAccumulation = computed(() => monthlySavings.value + monthlyHousingFund.value);

const monthsToGoal = computed(() => {
  if (totalMonthlyAccumulation.value <= 0) return Infinity;
  return Math.ceil(goalAmount.value / totalMonthlyAccumulation.value);
});

const goalDate = computed(() => {
  if (!isFinite(monthsToGoal.value) || monthsToGoal.value <= 0) return "无法达成";
  const d = new Date();
  d.setMonth(d.getMonth() + monthsToGoal.value);
  return `${d.getFullYear()}年${d.getMonth() + 1}月`;
});

const emergencyTarget = computed(() => totalCost.value * 4.5);

function loadSalaryData() {
  try {
    const data = localStorage.getItem(STORAGE_KEY_SALARY);
    const parsed = data ? JSON.parse(data) : [];
    if (parsed.length > 0) salaryData.value = parsed[0];
  } catch { salaryData.value = null; }
}

function loadCostData() {
  try {
    const data = localStorage.getItem(STORAGE_KEY_COST);
    if (data) Object.assign(costForm, JSON.parse(data));
  } catch { /* ignore */ }
}

watch(goalType, (val) => {
  const preset = goalPresets[val];
  if (val === "emergency") {
    goalAmount.value = Math.round(emergencyTarget.value);
  } else if (preset?.amount) {
    goalAmount.value = preset.amount;
  }
});

function formatMoney(val) {
  if (val === null || val === undefined || !isFinite(val)) return "0";
  return Number(val).toLocaleString("zh-CN");
}

onMounted(() => {
  loadCostData();
  loadSalaryData();
});
</script>

<template>
  <div class="page-stack">
    <div class="page-toolbar">
      <div>
        <h3>📊 财务规划</h3>
        <p>算清生活成本，规划储蓄目标，让每一分钱都有方向。</p>
      </div>
    </div>

    <el-card>
      <el-tabs v-model="activeTab">
        <el-tab-pane label="🏠 生活成本" name="cost">
          <el-row :gutter="24">
            <el-col :xs="24" :lg="12">
              <el-form label-position="top">
                <el-form-item label="🏙️ 所在城市">
                  <el-select v-model="costForm.city" style="width: 100%" @change="applyCityDefaults">
                    <el-option label="北京" value="beijing" />
                    <el-option label="上海" value="shanghai" />
                    <el-option label="广州" value="guangzhou" />
                    <el-option label="深圳" value="shenzhen" />
                    <el-option label="杭州" value="hangzhou" />
                    <el-option label="成都" value="chengdu" />
                    <el-option label="武汉" value="wuhan" />
                    <el-option label="南京" value="nanjing" />
                    <el-option label="西安" value="xian" />
                    <el-option label="长沙" value="changsha" />
                    <el-option label="其他" value="other" />
                  </el-select>
                  <div class="form-hint">选择城市后自动填入参考值，可按实际情况修改。</div>
                </el-form-item>
                <el-form-item label="🏠 住房（租金/月供）">
                  <el-input-number v-model="costForm.rent" :min="0" :step="100" style="width: 100%" />
                </el-form-item>
                <el-form-item label="💡 水电燃气">
                  <el-input-number v-model="costForm.utilities" :min="0" :step="50" style="width: 100%" />
                </el-form-item>
                <el-form-item label="🍜 餐饮">
                  <el-input-number v-model="costForm.food" :min="0" :step="100" style="width: 100%" />
                </el-form-item>
                <el-form-item label="🚇 交通">
                  <el-input-number v-model="costForm.transport" :min="0" :step="50" style="width: 100%" />
                </el-form-item>
                <el-form-item label="📱 通讯/网费">
                  <el-input-number v-model="costForm.communication" :min="0" :step="50" style="width: 100%" />
                </el-form-item>
                <el-form-item label="🛒 日用/购物">
                  <el-input-number v-model="costForm.daily" :min="0" :step="50" style="width: 100%" />
                </el-form-item>
                <el-form-item label="🎮 社交/娱乐">
                  <el-input-number v-model="costForm.entertainment" :min="0" :step="50" style="width: 100%" />
                </el-form-item>
                <el-form-item label="📦 其他">
                  <el-input-number v-model="costForm.other" :min="0" :step="100" style="width: 100%" />
                </el-form-item>
              </el-form>
              <el-button type="primary" @click="saveCostData" style="width: 100%;">💾 保存</el-button>
            </el-col>
            <el-col :xs="24" :lg="12">
              <div class="cost-summary">
                <div class="cost-total">
                  <div class="cost-total-label">月总支出</div>
                  <div class="cost-total-amount">¥{{ formatMoney(totalCost) }}</div>
                  <div class="cost-total-sub">日均 ¥{{ formatMoney(dailyCost) }}</div>
                </div>
                <div class="cost-breakdown">
                  <div class="cost-bar-item" v-if="costForm.rent">
                    <span>🏠 住房</span>
                    <div class="cost-bar"><div :style="{ width: (costForm.rent / totalCost * 100) + '%' }"></div></div>
                    <span class="cost-bar-val">¥{{ formatMoney(costForm.rent) }}</span>
                  </div>
                  <div class="cost-bar-item" v-if="costForm.food">
                    <span>🍜 餐饮</span>
                    <div class="cost-bar"><div :style="{ width: (costForm.food / totalCost * 100) + '%' }"></div></div>
                    <span class="cost-bar-val">¥{{ formatMoney(costForm.food) }}</span>
                  </div>
                  <div class="cost-bar-item" v-if="costForm.transport">
                    <span>🚇 交通</span>
                    <div class="cost-bar"><div :style="{ width: (costForm.transport / totalCost * 100) + '%' }"></div></div>
                    <span class="cost-bar-val">¥{{ formatMoney(costForm.transport) }}</span>
                  </div>
                  <div class="cost-bar-item" v-if="costForm.entertainment">
                    <span>🎮 娱乐</span>
                    <div class="cost-bar"><div :style="{ width: (costForm.entertainment / totalCost * 100) + '%' }"></div></div>
                    <span class="cost-bar-val">¥{{ formatMoney(costForm.entertainment) }}</span>
                  </div>
                </div>
                <div class="cost-tip" v-if="totalCost > 0">
                  💡 住房支出占收入的 30% 以内比较健康。当前住房占比：{{ costForm.rent > 0 ? Math.round(costForm.rent / totalCost * 100) : 0 }}%（占总支出）。
                </div>
              </div>
            </el-col>
          </el-row>
        </el-tab-pane>

        <el-tab-pane label="📈 理财规划" name="plan">
          <div v-if="!salaryData" class="plan-empty">
            <el-empty description="还没有薪资数据">
              <p style="color: var(--text-tertiary); margin-bottom: 16px;">先去「薪资计算器」算一下到手工资，数据会自动同步到这里。</p>
              <router-link to="/salary"><el-button type="primary">去计算薪资</el-button></router-link>
            </el-empty>
          </div>
          <div v-else>
            <el-alert type="success" :closable="false" style="margin-bottom: 20px;">
              <template #title>已同步薪资数据</template>
              月到手 <strong>¥{{ formatMoney(salaryData.takeHome) }}</strong> · 公积金月入 <strong>¥{{ formatMoney((salaryData.housingFund || 0) * 2) }}</strong>（个人+企业）
            </el-alert>

            <el-row :gutter="20">
              <el-col :xs="24" :lg="12">
                <el-card shadow="never" class="plan-card">
                  <h4>📊 月度收支</h4>
                  <div class="plan-row"><span>月到手收入</span><span class="plan-income">+¥{{ formatMoney(salaryData.takeHome) }}</span></div>
                  <div class="plan-row"><span>生活成本</span><span class="plan-cost">-¥{{ formatMoney(totalCost) }}</span></div>
                  <div class="plan-row plan-row-total"><span>= 月可储蓄（现金）</span><strong>¥{{ formatMoney(monthlySavings) }}</strong></div>
                </el-card>
              </el-col>
              <el-col :xs="24" :lg="12">
                <el-card shadow="never" class="plan-card">
                  <h4>🏠 隐藏资产（公积金）</h4>
                  <div class="plan-row"><span>每月公积金入账</span><span>¥{{ formatMoney(monthlyHousingFund) }}</span></div>
                  <div class="plan-row"><span>年度公积金积累</span><span>¥{{ formatMoney(monthlyHousingFund * 12) }}</span></div>
                  <div class="plan-row plan-row-total"><span>月总积累（现金+公积金）</span><strong>¥{{ formatMoney(totalMonthlyAccumulation) }}</strong></div>
                </el-card>
              </el-col>
            </el-row>

            <el-card style="margin-top: 16px;">
              <h4 style="margin: 0 0 16px;">🎯 储蓄目标</h4>
              <el-form label-position="top" inline>
                <el-form-item label="目标类型">
                  <el-select v-model="goalType" style="width: 200px;">
                    <el-option v-for="(p, k) in goalPresets" :key="k" :label="p.label" :value="k" />
                  </el-select>
                </el-form-item>
                <el-form-item label="目标金额（元）">
                  <el-input-number v-model="goalAmount" :min="1000" :step="5000" style="width: 200px;" />
                </el-form-item>
              </el-form>

              <div class="goal-result" v-if="totalMonthlyAccumulation > 0">
                <div class="goal-big">
                  按当前计划，达成 <strong>¥{{ formatMoney(goalAmount) }}</strong> 目标需要
                </div>
                <div class="goal-months">{{ monthsToGoal }} 个月</div>
                <div class="goal-date">预计 <strong>{{ goalDate }}</strong> 达成 🎉</div>
                <div class="goal-detail">
                  月储蓄 ¥{{ formatMoney(monthlySavings) }} + 公积金 ¥{{ formatMoney(monthlyHousingFund) }} = ¥{{ formatMoney(totalMonthlyAccumulation) }}/月
                </div>
              </div>
              <el-alert v-else type="warning" :closable="false" title="当前月支出超过收入，无法储蓄">
                建议先调整生活成本，或提高收入后再设定储蓄目标。
              </el-alert>
            </el-card>

            <el-card style="margin-top: 16px;">
              <h4 style="margin: 0 0 12px;">💡 理财建议</h4>
              <div class="advice-list">
                <div class="advice-item">💰 建议预留 <strong>¥{{ formatMoney(emergencyTarget) }}</strong> 作为应急基金（约4.5个月生活费）</div>
                <div class="advice-item">🏠 公积金是强制储蓄，离职/买房时可提取，别忘了算进你的资产</div>
                <div class="advice-item" v-if="monthlySavings > 0">📈 月可储蓄 ¥{{ formatMoney(monthlySavings) }}，建议 50% 存定期/货币基金，50% 灵活支配</div>
                <div class="advice-item" v-if="totalCost > salaryData.takeHome * 0.8">⚠️ 生活成本占收入超过80%，建议适当控制开支</div>
              </div>
            </el-card>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<style scoped>
.form-hint { font-size: 12px; color: var(--text-tertiary); margin-top: 4px; }

.cost-summary { padding: 16px; }
.cost-total { text-align: center; padding: 24px 0; }
.cost-total-label { font-size: 14px; color: var(--text-secondary); }
.cost-total-amount { font-size: 36px; font-weight: 800; color: var(--color-danger); margin: 4px 0; }
.cost-total-sub { font-size: 13px; color: var(--text-tertiary); }

.cost-breakdown { margin-top: 16px; display: flex; flex-direction: column; gap: 8px; }
.cost-bar-item { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.cost-bar-item > span:first-child { width: 60px; flex-shrink: 0; }
.cost-bar { flex: 1; height: 8px; background: var(--color-gray-100); border-radius: 4px; overflow: hidden; }
.cost-bar > div { height: 100%; background: var(--color-primary-400); border-radius: 4px; transition: width 0.3s; }
.cost-bar-val { width: 70px; text-align: right; font-weight: 600; flex-shrink: 0; }
.cost-tip { margin-top: 16px; padding: 10px 14px; background: var(--color-warm-light); border-radius: var(--radius-md); font-size: 13px; color: var(--text-secondary); line-height: 1.5; }

.plan-card { height: 100%; }
.plan-card h4 { margin: 0 0 12px; font-size: 15px; font-weight: 600; }
.plan-row { display: flex; justify-content: space-between; padding: 6px 0; font-size: 14px; color: var(--text-secondary); }
.plan-row-total { border-top: 1px dashed var(--border-color); padding-top: 10px; margin-top: 6px; font-weight: 600; color: var(--text-primary); }
.plan-income { color: var(--color-accent); font-weight: 600; }
.plan-cost { color: var(--color-danger); font-weight: 600; }

.goal-result { text-align: center; padding: 24px 0; }
.goal-big { font-size: 15px; color: var(--text-secondary); }
.goal-months { font-size: 48px; font-weight: 800; color: var(--color-accent); margin: 8px 0; }
.goal-date { font-size: 16px; color: var(--text-primary); }
.goal-detail { font-size: 13px; color: var(--text-tertiary); margin-top: 8px; }

.advice-list { display: flex; flex-direction: column; gap: 10px; }
.advice-item { padding: 10px 14px; background: var(--color-primary-50); border-radius: var(--radius-md); font-size: 13px; color: var(--text-secondary); line-height: 1.5; }
.advice-item strong { color: var(--text-primary); }

.plan-empty { padding: 40px 0; }
</style>
