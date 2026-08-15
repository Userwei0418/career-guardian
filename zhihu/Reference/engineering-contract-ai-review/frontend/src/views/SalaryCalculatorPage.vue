<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import html2canvas from "html2canvas";
import { useIdentity } from "../composables/useIdentity";

const { identityConfig, isIdentitySet } = useIdentity();
const STORAGE_KEY = "salary_calc_history";
const STORAGE_KEY_COST = "life_cost_data";
const STORAGE_KEY_PLANS = "savings_plans";

const activeTab = ref("salary");
const expandedSections = ref(["basic"]);

const form = reactive({
  monthlySalary: 10000,
  performancePay: 0,
  socialInsuranceBase: null,
  housingFundRatio: 12,
  city: "beijing",
  specialDeductions: 0,
  bonusMonth: 0,
  mealSubsidy: 0,
  transportSubsidy: 0,
  housingSubsidy: 0,
  communicationSubsidy: 0,
  hasSupplementaryMedical: false,
  hasSupplementaryHousing: false,
  supplementaryHousingRatio: 0,
});

const savedResults = ref([]);

const cities = {
  beijing:   { name: "北京", pension: 8, medical: 2, unemployment: 0.5, housingDefault: 12 },
  shanghai:  { name: "上海", pension: 8, medical: 2, unemployment: 0.5, housingDefault: 7 },
  guangzhou: { name: "广州", pension: 8, medical: 2, unemployment: 0.2, housingDefault: 12 },
  shenzhen:  { name: "深圳", pension: 8, medical: 2, unemployment: 0.3, housingDefault: 5 },
  hangzhou:  { name: "杭州", pension: 8, medical: 2, unemployment: 0.5, housingDefault: 12 },
  chengdu:   { name: "成都", pension: 8, medical: 2, unemployment: 0.4, housingDefault: 12 },
  wuhan:     { name: "武汉", pension: 8, medical: 2, unemployment: 0.3, housingDefault: 8 },
  nanjing:   { name: "南京", pension: 8, medical: 2, unemployment: 0.5, housingDefault: 10 },
  xian:      { name: "西安", pension: 8, medical: 2, unemployment: 0.3, housingDefault: 12 },
  changsha:  { name: "长沙", pension: 8, medical: 2, unemployment: 0.3, housingDefault: 12 },
  other:     { name: "其他城市", pension: 8, medical: 2, unemployment: 0.5, housingDefault: 12 },
};

const cityConfig = computed(() => cities[form.city] || cities.other);
const insuranceBase = computed(() => form.socialInsuranceBase || (form.monthlySalary + form.performancePay));

const pension = computed(() => Math.round(insuranceBase.value * cityConfig.value.pension / 100));
const medical = computed(() => Math.round(insuranceBase.value * cityConfig.value.medical / 100));
const unemployment = computed(() => Math.round(insuranceBase.value * cityConfig.value.unemployment / 100));
const housingFund = computed(() => Math.round(insuranceBase.value * form.housingFundRatio / 100));
const supplementaryHousing = computed(() => form.hasSupplementaryHousing ? Math.round(insuranceBase.value * form.supplementaryHousingRatio / 100) : 0);

const totalInsurance = computed(() => pension.value + medical.value + unemployment.value);
const totalDeduction = computed(() => totalInsurance.value + housingFund.value + supplementaryHousing.value);

const totalSubsidies = computed(() => form.mealSubsidy + form.transportSubsidy + form.housingSubsidy + form.communicationSubsidy);
const grossIncome = computed(() => form.monthlySalary + form.performancePay + totalSubsidies.value);

const taxableIncome = computed(() => {
  const base = grossIncome.value - totalDeduction.value - 5000 - form.specialDeductions;
  return Math.max(0, base);
});

const tax = computed(() => {
  const income = taxableIncome.value;
  if (income <= 0) return 0;
  if (income <= 3000) return Math.round(income * 0.03);
  if (income <= 12000) return Math.round(income * 0.10 - 210);
  if (income <= 25000) return Math.round(income * 0.20 - 1410);
  if (income <= 35000) return Math.round(income * 0.25 - 2660);
  if (income <= 55000) return Math.round(income * 0.30 - 4410);
  if (income <= 80000) return Math.round(income * 0.35 - 7160);
  return Math.round(income * 0.45 - 15160);
});

const takeHome = computed(() => grossIncome.value - totalDeduction.value - tax.value);
const effectiveRate = computed(() => {
  if (grossIncome.value <= 0) return "0";
  return ((tax.value / grossIncome.value) * 100).toFixed(1);
});

const employerCost = computed(() => {
  const base = insuranceBase.value;
  const employerPension = Math.round(base * 16 / 100);
  const employerMedical = Math.round(base * 9.8 / 100);
  const employerUnemployment = Math.round(base * 0.5 / 100);
  const employerWorkInjury = Math.round(base * 0.4 / 100);
  const employerMaternity = Math.round(base * 0.8 / 100);
  const employerHousing = housingFund.value + supplementaryHousing.value;
  const total = employerPension + employerMedical + employerUnemployment + employerWorkInjury + employerMaternity + employerHousing;
  return {
    pension: employerPension, medical: employerMedical, unemployment: employerUnemployment,
    workInjury: employerWorkInjury, maternity: employerMaternity, housing: employerHousing,
    total, grandTotal: grossIncome.value + total,
  };
});

const annualIncome = computed(() => {
  const monthly = takeHome.value;
  const bonus = form.bonusMonth > 0 ? grossIncome.value * form.bonusMonth : 0;
  return monthly * 12 + bonus;
});

function formatMoney(val) {
  if (val === null || val === undefined) return "0";
  return Number(val).toLocaleString("zh-CN");
}

watch(() => form.city, (newCity) => {
  const config = cities[newCity];
  if (config) form.housingFundRatio = config.housingDefault;
});

// ---- 保存/加载历史记录 ----
function loadHistory() {
  try {
    const data = localStorage.getItem(STORAGE_KEY);
    savedResults.value = data ? JSON.parse(data) : [];
  } catch { savedResults.value = []; }
}

function persistHistory() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(savedResults.value));
}

function saveResult() {
  const snapshot = {
    id: Date.now(),
    createdAt: new Date().toLocaleString("zh-CN"),
    city: form.city,
    cityName: cityConfig.value.name,
    monthlySalary: form.monthlySalary,
    performancePay: form.performancePay,
    housingFundRatio: form.housingFundRatio,
    socialInsuranceBase: form.socialInsuranceBase,
    specialDeductions: form.specialDeductions,
    bonusMonth: form.bonusMonth,
    mealSubsidy: form.mealSubsidy,
    transportSubsidy: form.transportSubsidy,
    housingSubsidy: form.housingSubsidy,
    communicationSubsidy: form.communicationSubsidy,
    hasSupplementaryMedical: form.hasSupplementaryMedical,
    hasSupplementaryHousing: form.hasSupplementaryHousing,
    supplementaryHousingRatio: form.supplementaryHousingRatio,
    totalSubsidies: totalSubsidies.value,
    totalDeduction: totalDeduction.value,
    tax: tax.value,
    takeHome: takeHome.value,
    annualIncome: annualIncome.value,
  };
  savedResults.value.unshift(snapshot);
  if (savedResults.value.length > 20) savedResults.value.pop();
  persistHistory();
  ElMessage.success("已保存");
}

function loadResult(item) {
  // 先设值，最后设 city（因为 city 的 watch 会覆盖公积金比例）
  form.monthlySalary = item.monthlySalary;
  form.performancePay = item.performancePay || 0;
  form.housingFundRatio = item.housingFundRatio || 12;
  form.socialInsuranceBase = item.socialInsuranceBase || null;
  form.specialDeductions = item.specialDeductions || 0;
  form.bonusMonth = item.bonusMonth || 0;
  form.mealSubsidy = item.mealSubsidy || 0;
  form.transportSubsidy = item.transportSubsidy || 0;
  form.housingSubsidy = item.housingSubsidy || 0;
  form.communicationSubsidy = item.communicationSubsidy || 0;
  form.hasSupplementaryMedical = item.hasSupplementaryMedical || false;
  form.hasSupplementaryHousing = item.hasSupplementaryHousing || false;
  form.supplementaryHousingRatio = item.supplementaryHousingRatio || 0;
  form.city = item.city; // 放最后，watch 会设默认公积金比例
  form.housingFundRatio = item.housingFundRatio || 12; // 再次覆盖 watch 的默认值
  ElMessage.success("已加载");
}

async function deleteResult(item) {
  try {
    await ElMessageBox.confirm("确定删除这条记录？", "提示", { type: "warning" });
    savedResults.value = savedResults.value.filter(r => r.id !== item.id);
    persistHistory();
  } catch { /* cancelled */ }
}

// ---- 海报导出 ----
const posterRef = ref(null);
const exportingPoster = ref(false);

async function exportPoster() {
  if (!posterRef.value) return;
  exportingPoster.value = true;
  try {
    const canvas = await html2canvas(posterRef.value, {
      scale: 2,
      backgroundColor: "#ffffff",
      useCORS: true,
    });
    canvas.toBlob((blob) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `薪资明细-${cityConfig.value.name}-${new Date().toLocaleDateString("zh-CN").replace(/\//g, "")}.png`;
      link.click();
      URL.revokeObjectURL(url);
      ElMessage.success("海报已保存");
    }, "image/png");
  } catch {
    ElMessage.error("导出失败，请重试");
  } finally {
    exportingPoster.value = false;
  }
}

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
  city: "beijing", rent: 3000, utilities: 200, food: 2500, transport: 400,
  communication: 150, daily: 500, entertainment: 500, other: 0,
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
function loadCostData() {
  try {
    const data = localStorage.getItem(STORAGE_KEY_COST);
    if (data) Object.assign(costForm, JSON.parse(data));
  } catch { /* ignore */ }
}

// ---- 理财规划 ----
const salaryDataForPlan = ref(null);
const goalAmount = ref(50000);
const goalType = ref("emergency");
const goalPresets = {
  emergency: { label: "应急基金（3~6个月生活费）" },
  house: { label: "买房首付", amount: 200000 },
  travel: { label: "旅行基金", amount: 20000 },
  custom: { label: "自定义目标", amount: 50000 },
};

const monthlySavings = computed(() => salaryDataForPlan.value ? Math.max(0, salaryDataForPlan.value.takeHome - totalCost.value) : 0);
const monthlyHousingFund = computed(() => salaryDataForPlan.value ? (salaryDataForPlan.value.housingFund || 0) * 2 : 0);
const totalMonthlyAccumulation = computed(() => monthlySavings.value + monthlyHousingFund.value);
const monthsToGoal = computed(() => totalMonthlyAccumulation.value > 0 ? Math.ceil(goalAmount.value / totalMonthlyAccumulation.value) : Infinity);
const goalDate = computed(() => {
  if (!isFinite(monthsToGoal.value) || monthsToGoal.value <= 0) return "无法达成";
  const d = new Date(); d.setMonth(d.getMonth() + monthsToGoal.value);
  return `${d.getFullYear()}年${d.getMonth() + 1}月`;
});
const emergencyTarget = computed(() => totalCost.value * 4.5);

function loadSalaryDataForPlan() {
  try {
    const data = localStorage.getItem(STORAGE_KEY);
    const parsed = data ? JSON.parse(data) : [];
    if (parsed.length > 0) salaryDataForPlan.value = parsed[0];
  } catch { salaryDataForPlan.value = null; }
}

watch(goalType, (val) => {
  if (val === "emergency") goalAmount.value = Math.round(emergencyTarget.value);
  else if (goalPresets[val]?.amount) goalAmount.value = goalPresets[val].amount;
});

// ---- 攒钱计划 ----
const savingsPlans = ref([]);
const showPlanDialog = ref(false);
const planForm = reactive({ name: "", goalAmount: 50000, currentAmount: 0 });

function loadPlans() {
  try {
    const data = localStorage.getItem(STORAGE_KEY_PLANS);
    savingsPlans.value = data ? JSON.parse(data) : [];
  } catch { savingsPlans.value = []; }
}

function persistPlans() {
  localStorage.setItem(STORAGE_KEY_PLANS, JSON.stringify(savingsPlans.value));
}

function openAddPlan() {
  planForm.name = "";
  planForm.goalAmount = 50000;
  planForm.currentAmount = 0;
  showPlanDialog.value = true;
}

function addPlan() {
  if (!planForm.name.trim()) { ElMessage.warning("请输入计划名称"); return; }
  const monthlyAcc = totalMonthlyAccumulation.value || monthlySavings.value || 0;
  const remaining = planForm.goalAmount - planForm.currentAmount;
  const months = monthlyAcc > 0 ? Math.ceil(remaining / monthlyAcc) : 0;
  const plan = {
    id: Date.now(),
    name: planForm.name.trim(),
    goalAmount: planForm.goalAmount,
    currentAmount: planForm.currentAmount,
    monthlySavings: monthlyAcc,
    monthsToGoal: months,
    createdAt: new Date().toLocaleDateString("zh-CN"),
  };
  savingsPlans.value.unshift(plan);
  persistPlans();
  showPlanDialog.value = false;
  ElMessage.success("计划已创建");
}

function deletePlan(plan) {
  savingsPlans.value = savingsPlans.value.filter(p => p.id !== plan.id);
  persistPlans();
}

function planProgress(plan) {
  if (plan.goalAmount <= 0) return 0;
  return Math.min(100, Math.round((plan.currentAmount / plan.goalAmount) * 100));
}

// ---- 收支记录 ----
const STORAGE_KEY_RECORDS = "expense_records";
const expenseRecords = ref([]);
const showRecordDialog = ref(false);
const recordForm = reactive({ type: "expense", category: "food", amount: 0, note: "", date: new Date().toISOString().slice(0, 10) });

const expenseCategories = [
  { code: "rent", label: "🏠 住房", color: "#3B82F6" },
  { code: "food", label: "🍜 餐饮", color: "#F59E0B" },
  { code: "transport", label: "🚇 交通", color: "#10B981" },
  { code: "shopping", label: "🛒 日用", color: "#8B5CF6" },
  { code: "entertainment", label: "🎮 娱乐", color: "#EC4899" },
  { code: "utilities", label: "💡 水电", color: "#6366F1" },
  { code: "communication", label: "📱 通讯", color: "#14B8A6" },
  { code: "medical", label: "🏥 医疗", color: "#EF4444" },
  { code: "other", label: "📦 其他", color: "#6B7280" },
];

const incomeCategories = [
  { code: "salary", label: "💰 工资", color: "#10B981" },
  { code: "bonus", label: "🎁 奖金", color: "#F59E0B" },
  { code: "parttime", label: "💼 兼职", color: "#3B82F6" },
  { code: "other_income", label: "📦 其他", color: "#6B7280" },
];

function loadRecords() {
  try {
    const data = localStorage.getItem(STORAGE_KEY_RECORDS);
    expenseRecords.value = data ? JSON.parse(data) : [];
  } catch { expenseRecords.value = []; }
}

function persistRecords() {
  localStorage.setItem(STORAGE_KEY_RECORDS, JSON.stringify(expenseRecords.value));
}

function openAddRecord() {
  recordForm.type = "expense";
  recordForm.category = "food";
  recordForm.amount = 0;
  recordForm.note = "";
  recordForm.date = new Date().toISOString().slice(0, 10);
  showRecordDialog.value = true;
}

function addRecord() {
  if (recordForm.amount <= 0) { ElMessage.warning("请输入金额"); return; }
  const record = {
    id: Date.now(),
    type: recordForm.type,
    category: recordForm.category,
    amount: recordForm.amount,
    note: recordForm.note,
    date: recordForm.date,
  };
  expenseRecords.value.unshift(record);
  persistRecords();
  showRecordDialog.value = false;
  ElMessage.success("已记录");
}

function deleteRecord(record) {
  expenseRecords.value = expenseRecords.value.filter(r => r.id !== record.id);
  persistRecords();
}

const currentMonth = computed(() => new Date().toISOString().slice(0, 7));

const monthlyRecords = computed(() =>
  expenseRecords.value.filter(r => r.date.startsWith(currentMonth.value))
);

const monthlyIncome = computed(() =>
  monthlyRecords.value.filter(r => r.type === "income").reduce((sum, r) => sum + r.amount, 0)
);

const monthlyExpense = computed(() =>
  monthlyRecords.value.filter(r => r.type === "expense").reduce((sum, r) => sum + r.amount, 0)
);

const monthlyNet = computed(() => monthlyIncome.value - monthlyExpense.value);

const expenseByCategory = computed(() => {
  const map = {};
  monthlyRecords.value.filter(r => r.type === "expense").forEach(r => {
    map[r.category] = (map[r.category] || 0) + r.amount;
  });
  return Object.entries(map)
    .map(([code, amount]) => {
      const cat = expenseCategories.find(c => c.code === code);
      return { code, label: cat?.label || code, color: cat?.color || "#6B7280", amount, pct: monthlyExpense.value > 0 ? Math.round(amount / monthlyExpense.value * 100) : 0 };
    })
    .sort((a, b) => b.amount - a.amount);
});

function getCategoryLabel(code) {
  const all = [...expenseCategories, ...incomeCategories];
  return all.find(c => c.code === code)?.label || code;
}

// ---- 工资条解读 ----
const slipForm = reactive({
  baseSalary: 0, performancePay: 0, subsidies: 0,
  pension: 0, medical: 0, unemployment: 0, housingFund: 0,
  tax: 0, netPay: 0, city: "beijing",
});

const slipValidation = computed(() => {
  const city = cities[slipForm.city] || cities.other;
  const gross = slipForm.baseSalary + slipForm.performancePay + slipForm.subsidies;
  const insBase = slipForm.baseSalary + slipForm.performancePay;
  const issues = [];
  const checks = [];

  if (insBase > 0) {
    const expectedPension = Math.round(insBase * city.pension / 100);
    const expectedMedical = Math.round(insBase * city.medical / 100);
    const expectedUnemployment = Math.round(insBase * city.unemployment / 100);

    checks.push({ label: "养老保险", expected: expectedPension, actual: slipForm.pension, rate: city.pension + "%" });
    checks.push({ label: "医疗保险", expected: expectedMedical, actual: slipForm.medical, rate: city.medical + "%" });
    checks.push({ label: "失业保险", expected: expectedUnemployment, actual: slipForm.unemployment, rate: city.unemployment + "%" });

    if (Math.abs(slipForm.pension - expectedPension) > 10) issues.push(`养老扣除 ¥${slipForm.pension}，预期 ¥${expectedPension}（${city.pension}%），可能基数不对`);
    if (Math.abs(slipForm.medical - expectedMedical) > 10) issues.push(`医疗扣除 ¥${slipForm.medical}，预期 ¥${expectedMedical}（${city.medical}%），可能基数不对`);
    if (Math.abs(slipForm.unemployment - expectedUnemployment) > 10) issues.push(`失业扣除 ¥${slipForm.unemployment}，预期 ¥${expectedUnemployment}（${city.unemployment}%），可能基数不对`);
  }

  const expectedNet = gross - slipForm.pension - slipForm.medical - slipForm.unemployment - slipForm.housingFund - slipForm.tax;
  if (slipForm.netPay > 0 && Math.abs(slipForm.netPay - expectedNet) > 10) {
    issues.push(`实发工资 ¥${slipForm.netPay}，按各项扣除计算应为 ¥${expectedNet}，差额 ¥${Math.abs(slipForm.netPay - expectedNet)}`);
  }

  return { gross, issues, checks, expectedNet };
});

// ---- 年终奖计税优化 ----
const bonusForm = reactive({ annualSalary: 0, bonusAmount: 0 });

const bonusComparison = computed(() => {
  const salary = bonusForm.annualSalary;
  const bonus = bonusForm.bonusAmount;
  if (salary <= 0 || bonus <= 0) return null;

  const taxableSalary = Math.max(0, salary - 60000);
  let salaryTax = 0;
  if (taxableSalary > 0) {
    if (taxableSalary <= 36000) salaryTax = Math.round(taxableSalary * 0.03);
    else if (taxableSalary <= 144000) salaryTax = Math.round(taxableSalary * 0.10 - 2520);
    else if (taxableSalary <= 300000) salaryTax = Math.round(taxableSalary * 0.20 - 16920);
    else if (taxableSalary <= 420000) salaryTax = Math.round(taxableSalary * 0.25 - 31920);
    else if (taxableSalary <= 660000) salaryTax = Math.round(taxableSalary * 0.30 - 52920);
    else if (taxableSalary <= 960000) salaryTax = Math.round(taxableSalary * 0.35 - 85920);
    else salaryTax = Math.round(taxableSalary * 0.45 - 181920);
  }

  // 单独计税
  const bonusMonthly = bonus / 12;
  let separateBonusTax = 0;
  if (bonusMonthly <= 3000) separateBonusTax = Math.round(bonus * 0.03);
  else if (bonusMonthly <= 12000) separateBonusTax = Math.round(bonus * 0.10 - 210);
  else if (bonusMonthly <= 25000) separateBonusTax = Math.round(bonus * 0.20 - 1410);
  else if (bonusMonthly <= 35000) separateBonusTax = Math.round(bonus * 0.25 - 2660);
  else if (bonusMonthly <= 55000) separateBonusTax = Math.round(bonus * 0.30 - 4410);
  else if (bonusMonthly <= 80000) separateBonusTax = Math.round(bonus * 0.35 - 7160);
  else separateBonusTax = Math.round(bonus * 0.45 - 15160);

  // 合并计税
  const totalTaxable = Math.max(0, salary + bonus - 60000);
  let combinedTax = 0;
  if (totalTaxable > 0) {
    if (totalTaxable <= 36000) combinedTax = Math.round(totalTaxable * 0.03);
    else if (totalTaxable <= 144000) combinedTax = Math.round(totalTaxable * 0.10 - 2520);
    else if (totalTaxable <= 300000) combinedTax = Math.round(totalTaxable * 0.20 - 16920);
    else if (totalTaxable <= 420000) combinedTax = Math.round(totalTaxable * 0.25 - 31920);
    else if (totalTaxable <= 660000) combinedTax = Math.round(totalTaxable * 0.30 - 52920);
    else if (totalTaxable <= 960000) combinedTax = Math.round(totalTaxable * 0.35 - 85920);
    else combinedTax = Math.round(totalTaxable * 0.45 - 181920);
  }
  const combinedBonusTax = combinedTax - salaryTax;

  const saving = combinedBonusTax - separateBonusTax;

  return {
    salaryTax, separateBonusTax, combinedBonusTax,
    separateTotal: salaryTax + separateBonusTax,
    combinedTotal: combinedTax,
    saving,
    recommend: saving > 0 ? "separate" : "combined",
  };
});

onMounted(() => {
  loadHistory();
  loadCostData();
  loadSalaryDataForPlan();
  loadPlans();
  loadRecords();
});
</script>

<template>
  <div class="page-stack">
    <div class="page-toolbar">
      <div>
        <h3>💰 薪资与财务规划</h3>
        <p>算薪资、算生活、算储蓄，一站式搞定你的钱袋子。</p>
      </div>
    </div>

    <div v-if="identityConfig?.salaryTip" class="identity-tip-inline">
      {{ identityConfig.icon }} {{ identityConfig.salaryTip }}
    </div>

    <el-card>
      <el-tabs v-model="activeTab">
        <el-tab-pane label="💰 薪资计算" name="salary">

    <el-row :gutter="24">
      <!-- 左侧：输入区（折叠面板） -->
      <el-col :xs="24" :lg="10">
        <div class="input-panel">
          <el-collapse v-model="expandedSections">
            <el-collapse-item title="💼 基本薪资" name="basic">
              <el-form label-position="top" size="small">
                <el-form-item label="基本月薪（元）">
                  <el-input-number v-model="form.monthlySalary" :min="0" :max="200000" :step="500" style="width: 100%" />
                </el-form-item>
                <el-form-item label="绩效工资（元/月）">
                  <el-input-number v-model="form.performancePay" :min="0" :max="100000" :step="500" style="width: 100%" />
                  <div class="form-hint">⚠️ 填期望值或平均值，绩效不保证100%拿到</div>
                </el-form-item>
                <el-form-item label="🏙️ 所在城市">
                  <el-select v-model="form.city" style="width: 100%">
                    <el-option v-for="(cfg, key) in cities" :key="key" :label="cfg.name" :value="key" />
                  </el-select>
                </el-form-item>
                <el-form-item label="🏦 社保缴费基数（元）">
                  <el-input-number v-model="form.socialInsuranceBase" :min="0" :max="200000" :step="500" placeholder="默认=月薪+绩效" style="width: 100%" />
                </el-form-item>
                <el-form-item :label="`🏠 公积金比例（${form.housingFundRatio}%）`">
                  <el-slider v-model="form.housingFundRatio" :min="5" :max="12" :step="1" show-stops />
                </el-form-item>
              </el-form>
            </el-collapse-item>

            <el-collapse-item name="subsidy">
              <template #title>🎁 补贴津贴 <el-tag v-if="totalSubsidies > 0" size="small" type="success" style="margin-left: 8px;">+¥{{ formatMoney(totalSubsidies) }}</el-tag></template>
              <el-form label-position="top" size="small">
                <el-form-item label="🍚 餐补"><el-input-number v-model="form.mealSubsidy" :min="0" :step="100" style="width: 100%" /></el-form-item>
                <el-form-item label="🚗 交通补贴"><el-input-number v-model="form.transportSubsidy" :min="0" :step="100" style="width: 100%" /></el-form-item>
                <el-form-item label="🏠 住房补贴"><el-input-number v-model="form.housingSubsidy" :min="0" :step="100" style="width: 100%" /></el-form-item>
                <el-form-item label="📱 通讯补贴"><el-input-number v-model="form.communicationSubsidy" :min="0" :step="100" style="width: 100%" /></el-form-item>
              </el-form>
            </el-collapse-item>

            <el-collapse-item name="insurance">
              <template #title>🛡️ 六险一金 <el-tag v-if="form.hasSupplementaryHousing || form.hasSupplementaryMedical" size="small" type="warning" style="margin-left: 8px;">已启用</el-tag></template>
              <el-form label-position="top" size="small">
                <el-form-item><el-checkbox v-model="form.hasSupplementaryHousing">补充住房公积金</el-checkbox></el-form-item>
                <el-form-item v-if="form.hasSupplementaryHousing" :label="`补充比例（${form.supplementaryHousingRatio}%）`">
                  <el-slider v-model="form.supplementaryHousingRatio" :min="1" :max="5" :step="1" show-stops />
                </el-form-item>
                <el-form-item><el-checkbox v-model="form.hasSupplementaryMedical">补充医疗保险</el-checkbox></el-form-item>
              </el-form>
            </el-collapse-item>

            <el-collapse-item name="other">
              <template #title>📝 其他扣除</template>
              <el-form label-position="top" size="small">
                <el-form-item label="专项附加扣除（元/月）">
                  <el-input-number v-model="form.specialDeductions" :min="0" :step="100" style="width: 100%" />
                  <div class="form-hint">子女教育、住房贷款/租金、赡养老人、婴幼儿照护等</div>
                </el-form-item>
                <el-form-item label="年终奖（月数）">
                  <el-input-number v-model="form.bonusMonth" :min="0" :max="12" :step="0.5" style="width: 100%" />
                </el-form-item>
              </el-form>
            </el-collapse-item>
          </el-collapse>

          <div class="input-actions">
            <el-button type="primary" style="flex: 1;" @click="saveResult">💾 保存</el-button>
            <el-button :loading="exportingPoster" style="flex: 1;" @click="exportPoster">📤 海报</el-button>
            <el-button style="flex: 1;" @click="Object.assign(form, { monthlySalary: 10000, performancePay: 0, mealSubsidy: 0, transportSubsidy: 0, housingSubsidy: 0, communicationSubsidy: 0, specialDeductions: 0, bonusMonth: 0, hasSupplementaryHousing: false, hasSupplementaryMedical: false, supplementaryHousingRatio: 0, socialInsuranceBase: null })">🔄 重置</el-button>
          </div>
        </div>
      </el-col>

      <!-- 右侧：结果面板（sticky） -->
      <el-col :xs="24" :lg="14">
        <div class="result-panel">
          <el-card class="result-card" shadow="never">
            <div class="take-home-highlight">
              <div class="take-home-label">每月实际到手</div>
              <div class="take-home-amount">¥ {{ formatMoney(takeHome) }}</div>
              <div class="take-home-sub">
                税前 {{ formatMoney(grossIncome) }} - 五险一金 {{ formatMoney(totalDeduction) }} - 个税 {{ formatMoney(tax) }}
              </div>
            </div>
            <el-divider />
            <div class="result-grid compact">
              <div class="result-item"><span class="result-label">养老 {{ cityConfig.pension }}%</span><span class="result-value">-¥{{ formatMoney(pension) }}</span></div>
              <div class="result-item"><span class="result-label">医疗 {{ cityConfig.medical }}%</span><span class="result-value">-¥{{ formatMoney(medical) }}</span></div>
              <div class="result-item"><span class="result-label">失业 {{ cityConfig.unemployment }}%</span><span class="result-value">-¥{{ formatMoney(unemployment) }}</span></div>
              <div class="result-item"><span class="result-label">公积金 {{ form.housingFundRatio }}%</span><span class="result-value">-¥{{ formatMoney(housingFund) }}</span></div>
              <div class="result-item" v-if="form.hasSupplementaryHousing"><span class="result-label">补充公积金 {{ form.supplementaryHousingRatio }}%</span><span class="result-value">-¥{{ formatMoney(supplementaryHousing) }}</span></div>
              <div class="result-item total"><span class="result-label">五险一金合计</span><span class="result-value">-¥{{ formatMoney(totalDeduction) }}</span></div>
              <div class="result-item"><span class="result-label">个人所得税</span><span class="result-value tax">-¥{{ formatMoney(tax) }}</span></div>
              <div class="result-item"><span class="result-label">实际税率</span><span class="result-value">{{ effectiveRate }}%</span></div>
            </div>
            <el-divider />
            <div class="result-stats-row">
              <div class="result-stat"><span>📅 年度到手</span><strong>¥{{ formatMoney(annualIncome) }}</strong></div>
              <div class="result-stat"><span>🏢 企业成本</span><strong>¥{{ formatMoney(employerCost.grandTotal) }}/月</strong></div>
              <div class="result-stat"><span>🏠 公积金月入</span><strong>¥{{ formatMoney(housingFund * 2) }}</strong></div>
            </div>
          </el-card>

          <el-card v-if="savedResults.length" style="margin-top: 12px;" shadow="never">
            <template #header><div class="card-header"><span>📋 已保存方案</span><el-tag size="small" type="info">{{ savedResults.length }}</el-tag></div></template>
            <div class="history-list">
              <div v-for="item in savedResults" :key="item.id" class="history-item">
                <div class="history-main" @click="loadResult(item)">
                  <div class="history-title">{{ item.cityName }} · 税前 ¥{{ formatMoney(item.monthlySalary + (item.performancePay || 0)) }}</div>
                  <div class="history-detail">到手 ¥{{ formatMoney(item.takeHome) }}/月</div>
                </div>
                <el-button text type="danger" size="small" @click="deleteResult(item)">×</el-button>
              </div>
            </div>
          </el-card>
        </div>
      </el-col>
    </el-row>

        </el-tab-pane>

        <el-tab-pane label="🏠 生活成本" name="cost">
          <el-row :gutter="24">
            <el-col :xs="24" :lg="12">
              <el-form label-position="top">
                <el-form-item label="🏙️ 所在城市">
                  <el-select v-model="costForm.city" style="width: 100%" @change="applyCityDefaults">
                    <el-option label="北京" value="beijing" /><el-option label="上海" value="shanghai" />
                    <el-option label="广州" value="guangzhou" /><el-option label="深圳" value="shenzhen" />
                    <el-option label="杭州" value="hangzhou" /><el-option label="成都" value="chengdu" />
                    <el-option label="武汉" value="wuhan" /><el-option label="南京" value="nanjing" />
                    <el-option label="西安" value="xian" /><el-option label="长沙" value="changsha" />
                    <el-option label="其他" value="other" />
                  </el-select>
                  <div class="form-hint">选择城市后自动填入参考值，可按实际情况修改。</div>
                </el-form-item>
                <el-form-item label="🏠 住房（租金/月供）"><el-input-number v-model="costForm.rent" :min="0" :step="100" style="width: 100%" /></el-form-item>
                <el-form-item label="💡 水电燃气"><el-input-number v-model="costForm.utilities" :min="0" :step="50" style="width: 100%" /></el-form-item>
                <el-form-item label="🍜 餐饮"><el-input-number v-model="costForm.food" :min="0" :step="100" style="width: 100%" /></el-form-item>
                <el-form-item label="🚇 交通"><el-input-number v-model="costForm.transport" :min="0" :step="50" style="width: 100%" /></el-form-item>
                <el-form-item label="📱 通讯/网费"><el-input-number v-model="costForm.communication" :min="0" :step="50" style="width: 100%" /></el-form-item>
                <el-form-item label="🛒 日用/购物"><el-input-number v-model="costForm.daily" :min="0" :step="50" style="width: 100%" /></el-form-item>
                <el-form-item label="🎮 社交/娱乐"><el-input-number v-model="costForm.entertainment" :min="0" :step="50" style="width: 100%" /></el-form-item>
                <el-form-item label="📦 其他"><el-input-number v-model="costForm.other" :min="0" :step="100" style="width: 100%" /></el-form-item>
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
                  <div class="cost-bar-item" v-if="costForm.rent"><span>🏠 住房</span><div class="cost-bar"><div :style="{ width: (costForm.rent / totalCost * 100) + '%' }"></div></div><span class="cost-bar-val">¥{{ formatMoney(costForm.rent) }}</span></div>
                  <div class="cost-bar-item" v-if="costForm.food"><span>🍜 餐饮</span><div class="cost-bar"><div :style="{ width: (costForm.food / totalCost * 100) + '%' }"></div></div><span class="cost-bar-val">¥{{ formatMoney(costForm.food) }}</span></div>
                  <div class="cost-bar-item" v-if="costForm.transport"><span>🚇 交通</span><div class="cost-bar"><div :style="{ width: (costForm.transport / totalCost * 100) + '%' }"></div></div><span class="cost-bar-val">¥{{ formatMoney(costForm.transport) }}</span></div>
                  <div class="cost-bar-item" v-if="costForm.entertainment"><span>🎮 娱乐</span><div class="cost-bar"><div :style="{ width: (costForm.entertainment / totalCost * 100) + '%' }"></div></div><span class="cost-bar-val">¥{{ formatMoney(costForm.entertainment) }}</span></div>
                </div>
              </div>
            </el-col>
          </el-row>
        </el-tab-pane>

        <el-tab-pane label="📈 理财规划" name="plan">
          <div v-if="!salaryDataForPlan" style="padding: 40px 0;">
            <el-empty description="还没有薪资数据，请先在「薪资计算」Tab 中计算并保存方案">
              <el-button type="primary" @click="activeTab = 'salary'">去计算薪资</el-button>
            </el-empty>
          </div>
          <div v-else>
            <el-alert type="success" :closable="false" style="margin-bottom: 20px;">
              <template #title>已同步薪资数据</template>
              月到手 <strong>¥{{ formatMoney(salaryDataForPlan.takeHome) }}</strong> · 公积金月入 <strong>¥{{ formatMoney(monthlyHousingFund) }}</strong>（个人+企业）
            </el-alert>
            <el-row :gutter="20">
              <el-col :xs="24" :lg="12">
                <el-card shadow="never" class="plan-card">
                  <h4>📊 月度收支</h4>
                  <div class="plan-row"><span>月到手收入</span><span class="plan-income">+¥{{ formatMoney(salaryDataForPlan.takeHome) }}</span></div>
                  <div class="plan-row"><span>生活成本</span><span class="plan-cost">-¥{{ formatMoney(totalCost) }}</span></div>
                  <div class="plan-row plan-row-total"><span>= 月可储蓄</span><strong>¥{{ formatMoney(monthlySavings) }}</strong></div>
                </el-card>
              </el-col>
              <el-col :xs="24" :lg="12">
                <el-card shadow="never" class="plan-card">
                  <h4>🏠 隐藏资产（公积金）</h4>
                  <div class="plan-row"><span>每月公积金入账</span><span>¥{{ formatMoney(monthlyHousingFund) }}</span></div>
                  <div class="plan-row"><span>年度公积金积累</span><span>¥{{ formatMoney(monthlyHousingFund * 12) }}</span></div>
                  <div class="plan-row plan-row-total"><span>月总积累</span><strong>¥{{ formatMoney(totalMonthlyAccumulation) }}</strong></div>
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
                <div class="goal-big">按当前计划，达成 <strong>¥{{ formatMoney(goalAmount) }}</strong> 目标需要</div>
                <div class="goal-months">{{ monthsToGoal }} 个月</div>
                <div class="goal-date">预计 <strong>{{ goalDate }}</strong> 达成 🎉</div>
                <div class="goal-detail">月储蓄 ¥{{ formatMoney(monthlySavings) }} + 公积金 ¥{{ formatMoney(monthlyHousingFund) }} = ¥{{ formatMoney(totalMonthlyAccumulation) }}/月</div>
              </div>
              <el-alert v-else type="warning" :closable="false" title="当前月支出超过收入，无法储蓄" />
            </el-card>
            <el-card style="margin-top: 16px;">
              <h4 style="margin: 0 0 12px;">💡 理财建议</h4>
              <div class="advice-list">
                <div class="advice-item">💰 建议预留 <strong>¥{{ formatMoney(emergencyTarget) }}</strong> 作为应急基金（约4.5个月生活费）</div>
                <div class="advice-item">🏠 公积金是强制储蓄，离职/买房时可提取，别忘了算进你的资产</div>
                <div class="advice-item" v-if="monthlySavings > 0">📈 月可储蓄 ¥{{ formatMoney(monthlySavings) }}，建议 50% 存定期/货币基金，50% 灵活支配</div>
              </div>
            </el-card>

            <el-card style="margin-top: 16px;">
              <template #header>
                <div class="card-header">
                  <span>🎯 我的攒钱计划</span>
                  <el-button type="primary" size="small" @click="openAddPlan">+ 新建计划</el-button>
                </div>
              </template>
              <div v-if="!savingsPlans.length" style="text-align: center; padding: 24px 0; color: var(--text-tertiary);">
                还没有攒钱计划，创建一个开始你的储蓄之旅吧 💪
              </div>
              <div v-else class="plans-list">
                <div v-for="plan in savingsPlans" :key="plan.id" class="plan-card">
                  <div class="plan-card-header">
                    <strong>{{ plan.name }}</strong>
                    <el-button text type="danger" size="small" @click="deletePlan(plan)">删除</el-button>
                  </div>
                  <div class="plan-progress-bar">
                    <div class="plan-progress-fill" :style="{ width: planProgress(plan) + '%' }"></div>
                  </div>
                  <div class="plan-card-stats">
                    <span>已存 <strong>¥{{ formatMoney(plan.currentAmount) }}</strong></span>
                    <span>目标 <strong>¥{{ formatMoney(plan.goalAmount) }}</strong></span>
                    <span>{{ planProgress(plan) }}%</span>
                  </div>
                  <div class="plan-card-footer" v-if="plan.monthlySavings > 0 && planProgress(plan) < 100">
                    每月存 ¥{{ formatMoney(plan.monthlySavings) }}，还需 <strong>{{ plan.monthsToGoal }} 个月</strong>
                  </div>
                  <div class="plan-card-footer done" v-else-if="planProgress(plan) >= 100">
                    🎉 目标已达成！
                  </div>
                </div>
              </div>
            </el-card>
          </div>
        </el-tab-pane>

        <el-tab-pane label="📝 收支记录" name="records">
          <div class="records-header">
            <div class="records-summary">
              <div class="records-stat income"><span>本月收入</span><strong>¥{{ formatMoney(monthlyIncome) }}</strong></div>
              <div class="records-stat expense"><span>本月支出</span><strong>¥{{ formatMoney(monthlyExpense) }}</strong></div>
              <div class="records-stat" :class="monthlyNet >= 0 ? 'income' : 'expense'"><span>本月结余</span><strong>¥{{ formatMoney(monthlyNet) }}</strong></div>
            </div>
            <el-button type="primary" @click="openAddRecord">+ 记一笔</el-button>
          </div>

          <div v-if="expenseByCategory.length" class="category-breakdown">
            <h4 style="margin: 0 0 12px; font-size: 14px;">支出分布</h4>
            <div v-for="cat in expenseByCategory" :key="cat.code" class="category-bar-item">
              <span class="category-label">{{ cat.label }}</span>
              <div class="category-bar"><div :style="{ width: cat.pct + '%', background: cat.color }"></div></div>
              <span class="category-amount">¥{{ formatMoney(cat.amount) }} ({{ cat.pct }}%)</span>
            </div>
          </div>

          <el-card v-if="monthlyRecords.length" shadow="never" style="margin-top: 16px;">
            <template #header><div class="card-header"><span>本月记录</span><el-tag size="small">{{ monthlyRecords.length }} 笔</el-tag></div></template>
            <div class="record-list">
              <div v-for="record in monthlyRecords" :key="record.id" class="record-item">
                <div class="record-info">
                  <span class="record-category">{{ getCategoryLabel(record.category) }}</span>
                  <span class="record-note" v-if="record.note">{{ record.note }}</span>
                  <span class="record-date">{{ record.date }}</span>
                </div>
                <div class="record-right">
                  <strong :style="{ color: record.type === 'income' ? 'var(--color-accent)' : 'var(--color-danger)' }">
                    {{ record.type === 'income' ? '+' : '-' }}¥{{ formatMoney(record.amount) }}
                  </strong>
                  <el-button text type="danger" size="small" @click="deleteRecord(record)">×</el-button>
                </div>
              </div>
            </div>
          </el-card>
          <el-empty v-else description="本月还没有记录，点击「记一笔」开始记账吧" />
        </el-tab-pane>

        <el-tab-pane label="🔍 工资条解读" name="slip">
          <el-row :gutter="20">
            <el-col :xs="24" :lg="12">
              <el-form label-position="top" size="small">
                <el-form-item label="城市">
                  <el-select v-model="slipForm.city" style="width: 100%">
                    <el-option v-for="(c, k) in cities" :key="k" :label="c.name" :value="k" />
                  </el-select>
                </el-form-item>
                <el-form-item label="应发工资（基本+绩效+补贴）"><el-input-number v-model="slipForm.baseSalary" :min="0" :step="500" style="width: 100%" /></el-form-item>
                <el-form-item label="养老扣除"><el-input-number v-model="slipForm.pension" :min="0" style="width: 100%" /></el-form-item>
                <el-form-item label="医疗扣除"><el-input-number v-model="slipForm.medical" :min="0" style="width: 100%" /></el-form-item>
                <el-form-item label="失业扣除"><el-input-number v-model="slipForm.unemployment" :min="0" style="width: 100%" /></el-form-item>
                <el-form-item label="公积金扣除"><el-input-number v-model="slipForm.housingFund" :min="0" style="width: 100%" /></el-form-item>
                <el-form-item label="个税扣除"><el-input-number v-model="slipForm.tax" :min="0" style="width: 100%" /></el-form-item>
                <el-form-item label="实发工资"><el-input-number v-model="slipForm.netPay" :min="0" style="width: 100%" /></el-form-item>
              </el-form>
            </el-col>
            <el-col :xs="24" :lg="12">
              <el-card v-if="slipValidation.checks.length" shadow="never">
                <template #header><div class="card-header"><span>校验结果</span></div></template>
                <div v-for="check in slipValidation.checks" :key="check.label" class="slip-check">
                  <span>{{ check.label }}（{{ check.rate }}）</span>
                  <span>预期 ¥{{ formatMoney(check.expected) }}</span>
                  <span>实际 ¥{{ formatMoney(check.actual) }}</span>
                  <el-tag :type="Math.abs(check.expected - check.actual) <= 10 ? 'success' : 'danger'" size="small">
                    {{ Math.abs(check.expected - check.actual) <= 10 ? '✓' : '✗ 差异 ¥' + Math.abs(check.expected - check.actual) }}
                  </el-tag>
                </div>
                <el-divider />
                <div class="slip-check"><span>应发合计</span><strong>¥{{ formatMoney(slipValidation.gross) }}</strong></div>
                <div class="slip-check"><span>预期实发</span><strong>¥{{ formatMoney(slipValidation.expectedNet) }}</strong></div>
              </el-card>
              <el-alert v-if="slipValidation.issues.length" type="warning" :closable="false" style="margin-top: 12px;">
                <template #title>发现 {{ slipValidation.issues.length }} 个异常</template>
                <ul style="margin: 4px 0 0; padding-left: 16px;">
                  <li v-for="(issue, i) in slipValidation.issues" :key="i">{{ issue }}</li>
                </ul>
              </el-alert>
              <el-alert v-else-if="slipValidation.checks.length" type="success" :closable="false" style="margin-top: 12px;" title="工资条校验通过，未发现异常 ✓" />
            </el-col>
          </el-row>
        </el-tab-pane>

        <el-tab-pane label="🧮 年终奖优化" name="bonus">
          <el-row :gutter="20">
            <el-col :xs="24" :lg="10">
              <el-form label-position="top" size="small">
                <el-form-item label="年应纳税所得额（年薪 - 6万 - 专项扣除）">
                  <el-input-number v-model="bonusForm.annualSalary" :min="0" :step="10000" style="width: 100%" />
                </el-form-item>
                <el-form-item label="年终奖金额">
                  <el-input-number v-model="bonusForm.bonusAmount" :min="0" :step="5000" style="width: 100%" />
                </el-form-item>
              </el-form>
            </el-col>
            <el-col :xs="24" :lg="14">
              <div v-if="bonusComparison">
                <el-row :gutter="12" style="margin-bottom: 16px;">
                  <el-col :span="12">
                    <el-card shadow="never" :class="['bonus-option', bonusComparison.recommend === 'separate' ? 'bonus-recommended' : '']">
                      <h4>单独计税</h4>
                      <div class="bonus-detail"><span>工资个税</span><strong>¥{{ formatMoney(bonusComparison.salaryTax) }}</strong></div>
                      <div class="bonus-detail"><span>年终奖个税</span><strong>¥{{ formatMoney(bonusComparison.separateBonusTax) }}</strong></div>
                      <div class="bonus-detail bonus-total"><span>合计</span><strong>¥{{ formatMoney(bonusComparison.separateTotal) }}</strong></div>
                      <el-tag v-if="bonusComparison.recommend === 'separate'" type="success" style="margin-top: 8px;">推荐 ✓</el-tag>
                    </el-card>
                  </el-col>
                  <el-col :span="12">
                    <el-card shadow="never" :class="['bonus-option', bonusComparison.recommend === 'combined' ? 'bonus-recommended' : '']">
                      <h4>合并计税</h4>
                      <div class="bonus-detail"><span>工资个税</span><strong>¥{{ formatMoney(bonusComparison.salaryTax) }}</strong></div>
                      <div class="bonus-detail"><span>年终奖个税</span><strong>¥{{ formatMoney(bonusComparison.combinedBonusTax) }}</strong></div>
                      <div class="bonus-detail bonus-total"><span>合计</span><strong>¥{{ formatMoney(bonusComparison.combinedTotal) }}</strong></div>
                      <el-tag v-if="bonusComparison.recommend === 'combined'" type="success" style="margin-top: 8px;">推荐 ✓</el-tag>
                    </el-card>
                  </el-col>
                </el-row>
                <el-alert :type="bonusComparison.saving > 0 ? 'success' : 'info'" :closable="false">
                  <template #title>
                    {{ bonusComparison.saving > 0 ? `单独计税可省 ¥${formatMoney(bonusComparison.saving)}` : `合并计税可省 ¥${formatMoney(Math.abs(bonusComparison.saving))}` }}
                  </template>
                  建议向公司财务确认是否支持选择计税方式。部分公司默认单独计税，需要主动申请。
                </el-alert>
              </div>
              <el-empty v-else description="请输入年薪和年终奖金额" />
            </el-col>
          </el-row>
        </el-tab-pane>

      </el-tabs>
    </el-card>

    <!-- 新建攒钱计划弹窗 -->
    <el-dialog v-model="showPlanDialog" title="🎯 新建攒钱计划" width="420px">
      <el-form label-position="top">
        <el-form-item label="计划名称">
          <el-input v-model="planForm.name" placeholder="如：应急基金、买房首付、旅行基金" />
        </el-form-item>
        <el-form-item label="目标金额（元）">
          <el-input-number v-model="planForm.goalAmount" :min="1000" :step="5000" style="width: 100%" />
        </el-form-item>
        <el-form-item label="已存金额（元）">
          <el-input-number v-model="planForm.currentAmount" :min="0" :step="1000" style="width: 100%" />
          <div class="form-hint">如果已经开始存钱了，填上当前已存的金额</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPlanDialog = false">取消</el-button>
        <el-button type="primary" @click="addPlan">创建计划</el-button>
      </template>
    </el-dialog>

    <!-- 记一笔弹窗 -->
    <el-dialog v-model="showRecordDialog" title="📝 记一笔" width="420px">
      <el-form label-position="top">
        <el-form-item label="类型">
          <el-radio-group v-model="recordForm.type">
            <el-radio-button value="expense">支出</el-radio-button>
            <el-radio-button value="income">收入</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="recordForm.category" style="width: 100%">
            <el-option v-for="cat in (recordForm.type === 'expense' ? expenseCategories : incomeCategories)" :key="cat.code" :label="cat.label" :value="cat.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额（元）">
          <el-input-number v-model="recordForm.amount" :min="0.01" :step="10" style="width: 100%" />
        </el-form-item>
        <el-form-item label="日期">
          <el-input v-model="recordForm.date" type="date" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="recordForm.note" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRecordDialog = false">取消</el-button>
        <el-button type="primary" @click="addRecord">记录</el-button>
      </template>
    </el-dialog>

    <!-- 海报模板（隐藏，用于 html2canvas 截图） -->
    <div ref="posterRef" class="poster-template">
      <div class="poster-header">
        <span class="poster-brand">🛡️ 职护</span>
        <span class="poster-date">{{ new Date().toLocaleDateString("zh-CN") }}</span>
      </div>
      <div class="poster-city">{{ cityConfig.name }} · 薪资明细</div>
      <div class="poster-divider"></div>
      <div class="poster-section">
        <div class="poster-label">税前总收入</div>
        <div class="poster-amount">¥{{ formatMoney(grossIncome) }}/月</div>
      </div>
      <div class="poster-breakdown">
        <div class="poster-row"><span>基本月薪</span><span>¥{{ formatMoney(form.monthlySalary) }}</span></div>
        <div class="poster-row" v-if="form.performancePay"><span>绩效工资</span><span>¥{{ formatMoney(form.performancePay) }}</span></div>
        <div class="poster-row" v-if="totalSubsidies"><span>补贴合计</span><span>¥{{ formatMoney(totalSubsidies) }}</span></div>
      </div>
      <div class="poster-divider"></div>
      <div class="poster-breakdown">
        <div class="poster-row"><span>五险一金</span><span class="poster-deduct">-¥{{ formatMoney(totalDeduction) }}</span></div>
        <div class="poster-row"><span>个人所得税</span><span class="poster-deduct">-¥{{ formatMoney(tax) }}</span></div>
      </div>
      <div class="poster-divider"></div>
      <div class="poster-section poster-highlight">
        <div class="poster-label">💰 实际到手</div>
        <div class="poster-amount poster-amount-main">¥{{ formatMoney(takeHome) }}/月</div>
      </div>
      <div class="poster-stats">
        <div class="poster-stat"><span>📅 年度到手</span><strong>¥{{ formatMoney(annualIncome) }}</strong></div>
        <div class="poster-stat"><span>🏢 企业成本</span><strong>¥{{ formatMoney(employerCost.grandTotal) }}/月</strong></div>
        <div class="poster-stat"><span>🏠 公积金月入</span><strong>¥{{ formatMoney(housingFund * 2) }}</strong></div>
      </div>
      <div class="poster-footer">职护 · 你的职场全方位保障</div>
    </div>
  </div>
</template>

<style scoped>
.identity-tip-inline {
  padding: 10px 16px;
  background: var(--color-primary-50);
  border: 1px solid var(--color-primary-200);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}
.form-hint { font-size: 12px; color: var(--text-tertiary); margin-top: 4px; line-height: 1.5; }

/* ---- 左右分栏布局 ---- */
.input-panel { position: relative; }
.input-panel :deep(.el-collapse) { border: none; --el-collapse-header-height: 48px; }
.input-panel :deep(.el-collapse-item__header) { font-size: 14px; font-weight: 600; border-bottom: 1px solid var(--border-color-light); }
.input-panel :deep(.el-collapse-item__wrap) { border-bottom: 1px solid var(--border-color-light); }
.input-panel :deep(.el-collapse-item__content) { padding: 12px 0 4px; }
.input-panel :deep(.el-form-item) { margin-bottom: 12px; }
.input-panel :deep(.el-form-item__label) { font-size: 13px; padding-bottom: 4px; }

.input-actions { display: flex; gap: 8px; margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border-color-light); }

.result-panel { position: sticky; top: 80px; }
.result-card { border: none !important; background: var(--color-gray-50) !important; }
.result-grid.compact { gap: 6px; }
.result-grid.compact .result-item { padding: 4px 0; font-size: 13px; }

.result-stats-row { display: flex; gap: 16px; flex-wrap: wrap; }
.result-stat { flex: 1; min-width: 100px; text-align: center; padding: 8px; background: var(--bg-card); border-radius: var(--radius-md); border: 1px solid var(--border-color-light); }
.result-stat span { display: block; font-size: 12px; color: var(--text-tertiary); margin-bottom: 4px; }
.result-stat strong { font-size: 15px; color: var(--text-primary); }

.subsidy-note { margin-top: 12px; padding: 8px 12px; background: var(--color-primary-50); border-radius: var(--radius-md); font-size: 13px; color: var(--text-secondary); }
.info-box { margin-top: 16px; padding: 12px 16px; background: var(--color-warm-light); border: 1px solid var(--color-warm-border); border-radius: var(--radius-md); font-size: 13px; color: var(--text-secondary); line-height: 1.7; }
.info-box strong { color: var(--text-primary); }
.info-box p { margin: 4px 0; }

.take-home-highlight { text-align: center; padding: 24px 0 16px; }
.take-home-label { font-size: 15px; color: var(--text-secondary); margin-bottom: 8px; }
.take-home-amount { font-size: 42px; font-weight: 800; color: var(--color-accent); letter-spacing: -1px; }
.take-home-sub { font-size: 13px; color: var(--text-tertiary); margin-top: 8px; }

.result-grid { display: flex; flex-direction: column; gap: 10px; }
.result-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; font-size: 14px; }
.result-label { color: var(--text-secondary); }
.result-value { font-weight: 600; color: var(--text-primary); }
.result-value.tax { color: var(--color-danger); }
.result-item.total { border-top: 1px dashed var(--border-color); padding-top: 10px; margin-top: 4px; }
.result-item.total .result-label { font-weight: 600; color: var(--text-primary); }
.result-item.highlight { background: var(--color-accent-light); padding: 10px 12px; border-radius: var(--radius-md); margin-top: 8px; }
.result-item.highlight .result-value { color: var(--color-accent); font-size: 18px; }

.annual-summary { padding: 8px 0; }
.annual-row { display: flex; justify-content: space-between; align-items: center; font-size: 16px; }
.annual-row strong { color: var(--color-accent); font-size: 20px; }
.annual-row.sub { font-size: 13px; color: var(--text-tertiary); margin-top: 4px; }

.employer-hint { margin-top: 16px; padding: 12px 16px; background: var(--color-primary-50); border-radius: var(--radius-md); font-size: 13px; color: var(--text-secondary); line-height: 1.6; }

.history-list { display: flex; flex-direction: column; gap: 8px; }
.history-item {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 16px; border: 1px solid var(--border-color); border-radius: var(--radius-md);
  transition: all var(--transition-fast);
}
.history-item:hover { border-color: var(--color-primary-300); background: var(--bg-hover); }
.history-main { flex: 1; cursor: pointer; }
.history-title { font-weight: 600; font-size: 14px; color: var(--text-primary); }
.history-detail { font-size: 13px; color: var(--color-accent); margin-top: 2px; }
.history-time { font-size: 12px; color: var(--text-tertiary); margin-top: 2px; }

.el-divider { margin: 16px 0 !important; }

/* ---- 海报模板 ---- */
.poster-template {
  position: fixed;
  left: -9999px;
  top: 0;
  width: 380px;
  padding: 28px 24px;
  background: linear-gradient(180deg, #EFF6FF 0%, #FFFFFF 30%);
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  color: #1A1A2E;
}
.poster-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.poster-brand { font-size: 14px; font-weight: 700; color: #3B82F6; }
.poster-date { font-size: 12px; color: #A0A0B8; }
.poster-city { font-size: 20px; font-weight: 700; margin-bottom: 12px; }
.poster-divider { height: 1px; background: #E8E8F0; margin: 12px 0; }
.poster-section { margin: 8px 0; }
.poster-label { font-size: 13px; color: #5A5A7A; margin-bottom: 4px; }
.poster-amount { font-size: 24px; font-weight: 800; color: #1A1A2E; }
.poster-amount-main { color: #10B981; font-size: 32px; }
.poster-highlight { background: #ECFDF5; padding: 12px 16px; border-radius: 10px; margin: 12px 0; }
.poster-breakdown { display: flex; flex-direction: column; gap: 6px; }
.poster-row { display: flex; justify-content: space-between; font-size: 13px; color: #5A5A7A; }
.poster-deduct { color: #EF4444; }
.poster-stats { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; padding: 12px 16px; background: #F8FAFC; border-radius: 10px; }
.poster-stat { display: flex; justify-content: space-between; font-size: 13px; color: #5A5A7A; }
.poster-stat strong { color: #1A1A2E; font-weight: 700; }
.poster-footer { text-align: center; margin-top: 16px; padding-top: 12px; border-top: 1px solid #E8E8F0; font-size: 12px; color: #A0A0B8; }

/* ---- 生活成本 ---- */
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

/* ---- 理财规划 ---- */
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

/* ---- 攒钱计划 ---- */
.plans-list { display: flex; flex-direction: column; gap: 12px; }
.plan-card { padding: 14px 16px; border: 1px solid var(--border-color); border-radius: var(--radius-lg); transition: all var(--transition-fast); }
.plan-card:hover { border-color: var(--color-primary-300); }
.plan-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.plan-card-header strong { font-size: 15px; }
.plan-progress-bar { height: 8px; background: var(--color-gray-100); border-radius: 4px; overflow: hidden; margin-bottom: 8px; }
.plan-progress-fill { height: 100%; background: linear-gradient(90deg, var(--color-primary-400), var(--color-accent)); border-radius: 4px; transition: width 0.5s ease; }
.plan-card-stats { display: flex; justify-content: space-between; font-size: 13px; color: var(--text-secondary); }
.plan-card-stats strong { color: var(--text-primary); }
.plan-card-footer { margin-top: 8px; font-size: 12px; color: var(--text-tertiary); }
.plan-card-footer.done { color: var(--color-accent); font-weight: 600; font-size: 13px; }

/* ---- 收支记录 ---- */
.records-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
.records-summary { display: flex; gap: 16px; flex-wrap: wrap; }
.records-stat { text-align: center; padding: 12px 20px; background: var(--color-gray-50); border-radius: var(--radius-lg); border: 1px solid var(--border-color-light); min-width: 120px; }
.records-stat span { display: block; font-size: 12px; color: var(--text-tertiary); margin-bottom: 4px; }
.records-stat strong { font-size: 20px; }
.records-stat.income strong { color: var(--color-accent); }
.records-stat.expense strong { color: var(--color-danger); }

.category-breakdown { margin-bottom: 8px; }
.category-bar-item { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 13px; }
.category-label { width: 70px; flex-shrink: 0; }
.category-bar { flex: 1; height: 8px; background: var(--color-gray-100); border-radius: 4px; overflow: hidden; }
.category-bar > div { height: 100%; border-radius: 4px; transition: width 0.3s; }
.category-amount { width: 110px; text-align: right; flex-shrink: 0; font-weight: 500; }

.record-list { display: flex; flex-direction: column; gap: 6px; }
.record-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; border-radius: var(--radius-md); transition: background var(--transition-fast); }
.record-item:hover { background: var(--color-gray-50); }
.record-info { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.record-category { font-weight: 500; font-size: 14px; }
.record-note { font-size: 12px; color: var(--text-tertiary); }
.record-date { font-size: 12px; color: var(--text-tertiary); }
.record-right { display: flex; align-items: center; gap: 8px; }

/* ---- 工资条解读 ---- */
.slip-check { display: flex; align-items: center; gap: 12px; padding: 6px 0; font-size: 13px; }
.slip-check span:first-child { flex: 1; color: var(--text-secondary); }
.slip-check span:nth-child(2), .slip-check span:nth-child(3) { width: 80px; text-align: right; }

/* ---- 年终奖优化 ---- */
.bonus-option { height: 100%; transition: all var(--transition-base); }
.bonus-option h4 { margin: 0 0 12px; font-size: 15px; font-weight: 600; }
.bonus-recommended { border: 2px solid var(--color-accent) !important; background: var(--color-success-bg) !important; }
.bonus-detail { display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; color: var(--text-secondary); }
.bonus-detail strong { color: var(--text-primary); }
.bonus-total { border-top: 1px dashed var(--border-color); padding-top: 8px; margin-top: 4px; font-weight: 600; }
.bonus-total strong { font-size: 16px; color: var(--text-primary); }
</style>
