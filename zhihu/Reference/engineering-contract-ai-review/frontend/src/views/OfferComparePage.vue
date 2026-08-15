<script setup>
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

const cities = {
  beijing:   { name: "北京", pension: 8, medical: 2, unemployment: 0.5, housingDefault: 12, livingCost: 7000 },
  shanghai:  { name: "上海", pension: 8, medical: 2, unemployment: 0.5, housingDefault: 7, livingCost: 6800 },
  guangzhou: { name: "广州", pension: 8, medical: 2, unemployment: 0.2, housingDefault: 12, livingCost: 5500 },
  shenzhen:  { name: "深圳", pension: 8, medical: 2, unemployment: 0.3, housingDefault: 5, livingCost: 6000 },
  hangzhou:  { name: "杭州", pension: 8, medical: 2, unemployment: 0.5, housingDefault: 12, livingCost: 5500 },
  chengdu:   { name: "成都", pension: 8, medical: 2, unemployment: 0.4, housingDefault: 12, livingCost: 4000 },
  wuhan:     { name: "武汉", pension: 8, medical: 2, unemployment: 0.3, housingDefault: 8, livingCost: 3800 },
  nanjing:   { name: "南京", pension: 8, medical: 2, unemployment: 0.5, housingDefault: 10, livingCost: 4500 },
  xian:      { name: "西安", pension: 8, medical: 2, unemployment: 0.3, housingDefault: 12, livingCost: 3500 },
  changsha:  { name: "长沙", pension: 8, medical: 2, unemployment: 0.3, housingDefault: 12, livingCost: 3200 },
  other:     { name: "其他城市", pension: 8, medical: 2, unemployment: 0.5, housingDefault: 12, livingCost: 4000 },
};

function createOffer(name) {
  return { name, city: "beijing", baseSalary: 0, performancePay: 0, housingFundRatio: 12, mealSubsidy: 0, transportSubsidy: 0, bonusMonths: 0, livingCost: 0, useDefaultCost: true };
}

const offers = reactive([createOffer("Offer A"), createOffer("Offer B")]);

function addOffer() {
  if (offers.length >= 4) { ElMessage.warning("最多对比4个Offer"); return; }
  offers.push(createOffer(`Offer ${String.fromCharCode(65 + offers.length)}`));
}

function removeOffer(idx) {
  if (offers.length <= 2) { ElMessage.warning("至少保留2个Offer"); return; }
  offers.splice(idx, 1);
}

function calcOffer(o) {
  const city = cities[o.city] || cities.other;
  const gross = o.baseSalary + o.performancePay + o.mealSubsidy + o.transportSubsidy;
  const insBase = o.baseSalary + o.performancePay;
  const pension = Math.round(insBase * city.pension / 100);
  const medical = Math.round(insBase * city.medical / 100);
  const unemployment = Math.round(insBase * city.unemployment / 100);
  const housing = Math.round(insBase * o.housingFundRatio / 100);
  const totalDeduction = pension + medical + unemployment + housing;
  const taxable = Math.max(0, gross - totalDeduction - 5000);
  let tax = 0;
  if (taxable > 0) {
    if (taxable <= 3000) tax = Math.round(taxable * 0.03);
    else if (taxable <= 12000) tax = Math.round(taxable * 0.10 - 210);
    else if (taxable <= 25000) tax = Math.round(taxable * 0.20 - 1410);
    else if (taxable <= 35000) tax = Math.round(taxable * 0.25 - 2660);
    else if (taxable <= 55000) tax = Math.round(taxable * 0.30 - 4410);
    else if (taxable <= 80000) tax = Math.round(taxable * 0.35 - 7160);
    else tax = Math.round(taxable * 0.45 - 15160);
  }
  const takeHome = gross - totalDeduction - tax;
  const bonus = o.bonusMonths > 0 ? gross * o.bonusMonths : 0;
  const annualTakeHome = takeHome * 12 + bonus;
  const housingFundYearly = housing * 2 * 12;
  const realAnnual = annualTakeHome + housingFundYearly;
  const cost = o.useDefaultCost ? city.livingCost : o.livingCost;
  const monthlySavings = takeHome - cost;
  const annualSavings = monthlySavings * 12 + bonus;

  return {
    city: city.name, gross, totalDeduction, tax, takeHome,
    housing, housingFundYearly, bonus, annualTakeHome, realAnnual,
    cost, monthlySavings, annualSavings,
  };
}

const results = computed(() => offers.map(o => ({ offer: o, calc: calcOffer(o) })));

const bestOffer = computed(() => {
  if (results.value.length === 0) return null;
  return results.value.reduce((best, r) => r.calc.annualSavings > best.calc.annualSavings ? r : best);
});

function formatMoney(val) {
  if (val === null || val === undefined || !isFinite(val)) return "0";
  return Number(val).toLocaleString("zh-CN");
}
</script>

<template>
  <div class="page-stack">
    <div class="page-toolbar">
      <div>
        <h3>⚖️ Offer 对比器</h3>
        <p>不只看月薪，算清真实年包和生活成本后的实际储蓄，帮你做出最优选择。</p>
      </div>
    </div>

    <el-row :gutter="16">
      <el-col v-for="(offer, idx) in offers" :key="idx" :xs="24" :sm="12" :lg="offers.length <= 2 ? 12 : 8">
        <el-card>
          <template #header>
            <div class="card-header">
              <el-input v-model="offer.name" size="small" style="width: 120px; font-weight: 600;" />
              <el-button v-if="offers.length > 2" text type="danger" size="small" @click="removeOffer(idx)">删除</el-button>
            </div>
          </template>
          <el-form label-position="top" size="small">
            <el-form-item label="城市">
              <el-select v-model="offer.city" style="width: 100%">
                <el-option v-for="(c, k) in cities" :key="k" :label="c.name" :value="k" />
              </el-select>
            </el-form-item>
            <el-form-item label="基本月薪（元）">
              <el-input-number v-model="offer.baseSalary" :min="0" :step="500" style="width: 100%" />
            </el-form-item>
            <el-form-item label="绩效/月（元）">
              <el-input-number v-model="offer.performancePay" :min="0" :step="500" style="width: 100%" />
            </el-form-item>
            <el-form-item label="公积金比例">
              <el-slider v-model="offer.housingFundRatio" :min="5" :max="12" :step="1" show-stops />
            </el-form-item>
            <el-form-item label="月补贴合计（元）">
              <el-input-number v-model="offer.mealSubsidy" :min="0" :step="100" placeholder="餐补+交通+住房+通讯" style="width: 100%" />
            </el-form-item>
            <el-form-item label="年终奖（月数）">
              <el-input-number v-model="offer.bonusMonths" :min="0" :max="12" :step="0.5" style="width: 100%" />
            </el-form-item>
            <el-form-item>
              <el-checkbox v-model="offer.useDefaultCost">使用城市默认生活成本</el-checkbox>
            </el-form-item>
            <el-form-item v-if="!offer.useDefaultCost" label="月生活成本（元）">
              <el-input-number v-model="offer.livingCost" :min="0" :step="500" style="width: 100%" />
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="offers.length <= 2 ? 12 : 8" v-if="offers.length < 4">
        <el-card class="add-card" shadow="hover" @click="addOffer">
          <div class="add-offer">+ 添加 Offer</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card>
      <template #header><div class="card-header"><span>📊 对比结果</span></div></template>
      <el-table :data="results" stripe>
        <el-table-column label="" width="140">
          <template #default="{ row }"><strong>{{ row.offer.name }}</strong></template>
        </el-table-column>
        <el-table-column label="城市" width="80">
          <template #default="{ row }">{{ row.calc.city }}</template>
        </el-table-column>
        <el-table-column label="税前月薪" width="100">
          <template #default="{ row }">¥{{ formatMoney(row.calc.gross) }}</template>
        </el-table-column>
        <el-table-column label="月到手" width="100">
          <template #default="{ row }"><strong style="color: var(--color-accent)">¥{{ formatMoney(row.calc.takeHome) }}</strong></template>
        </el-table-column>
        <el-table-column label="真实年包" width="110">
          <template #default="{ row }">¥{{ formatMoney(row.calc.realAnnual) }}</template>
        </el-table-column>
        <el-table-column label="月生活成本" width="100">
          <template #default="{ row }">¥{{ formatMoney(row.calc.cost) }}</template>
        </el-table-column>
        <el-table-column label="月储蓄" width="100">
          <template #default="{ row }">
            <strong :style="{ color: row.calc.monthlySavings >= 0 ? 'var(--color-accent)' : 'var(--color-danger)' }">
              ¥{{ formatMoney(row.calc.monthlySavings) }}
            </strong>
          </template>
        </el-table-column>
        <el-table-column label="年储蓄" width="110">
          <template #default="{ row }">
            <strong :style="{ color: row.calc.annualSavings >= 0 ? 'var(--color-accent)' : 'var(--color-danger)' }">
              ¥{{ formatMoney(row.calc.annualSavings) }}
            </strong>
          </template>
        </el-table-column>
        <el-table-column label="公积金年入" width="100">
          <template #default="{ row }">¥{{ formatMoney(row.calc.housingFundYearly) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="bestOffer" class="recommendation-card">
      <div class="recommendation">
        <div class="rec-icon">🏆</div>
        <div>
          <h3>综合推荐：{{ bestOffer.offer.name }}</h3>
          <p>
            扣除生活成本后，<strong>{{ bestOffer.offer.name }}</strong> 每年能多存下
            <strong style="color: var(--color-accent)">¥{{ formatMoney(bestOffer.calc.annualSavings) }}</strong>，
            月到手 <strong>¥{{ formatMoney(bestOffer.calc.takeHome) }}</strong>，
            公积金年入 <strong>¥{{ formatMoney(bestOffer.calc.housingFundYearly) }}</strong>。
          </p>
          <p class="rec-note">
            💡 当然，选Offer不只看钱。还要综合考虑：成长空间、通勤距离、加班强度、团队氛围、城市发展前景。
            这个对比帮你理清"钱"的部分，其他维度需要你自己权衡。
          </p>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.add-card { cursor: pointer; display: flex; align-items: center; justify-content: center; min-height: 200px; border: 2px dashed var(--border-color-dark) !important; transition: all var(--transition-base); }
.add-card:hover { border-color: var(--color-primary-400) !important; background: var(--bg-hover); }
.add-offer { font-size: 16px; color: var(--text-tertiary); font-weight: 500; }

.recommendation-card { border: 2px solid var(--color-accent) !important; background: var(--color-success-bg) !important; }
.recommendation { display: flex; gap: 16px; align-items: flex-start; }
.rec-icon { font-size: 36px; flex-shrink: 0; }
.recommendation h3 { margin: 0 0 8px; font-size: 18px; color: var(--text-primary); }
.recommendation p { margin: 4px 0; font-size: 14px; color: var(--text-secondary); line-height: 1.6; }
.rec-note { font-size: 13px !important; color: var(--text-tertiary) !important; margin-top: 8px !important; padding: 8px 12px; background: rgba(255,255,255,0.5); border-radius: var(--radius-md); }
</style>
