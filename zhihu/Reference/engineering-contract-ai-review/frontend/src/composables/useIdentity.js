import { ref, computed } from "vue";

const STORAGE_KEY = "user_identity";

const IDENTITY_OPTIONS = {
  student: {
    code: "student",
    label: "在校学生",
    icon: "📚",
    description: "在校，正在或即将找实习",
    salaryTip: "实习生通常不缴五险一金，到手 ≈ 税前。但一定要签实习协议，明确薪资和工作内容。",
    recommendedSlugs: ["intern-and-contracts"],
    homeTips: [
      "建议你刷几段实习，积累经验和简历素材",
      "实习协议不等于劳动合同，不受劳动法保护",
      "实习期间受伤不能认定工伤，但可以要求民事赔偿",
    ],
  },
  intern: {
    code: "intern",
    label: "实习生",
    icon: "🎓",
    description: "正在实习中",
    salaryTip: "实习期不缴五险一金，到手 ≈ 税前。注意实习时长和工作内容是否和协议一致。",
    recommendedSlugs: ["intern-and-contracts", "five-insurance-one-fund"],
    homeTips: [
      "实习协议要明确：薪资、工时、工作内容、终止条件",
      "实习期间保留好工作记录，为秋招积累素材",
      "毕业后继续在同一公司工作，应重新签劳动合同",
    ],
  },
  freshGrad: {
    code: "freshGrad",
    label: "应届生",
    icon: "🎒",
    description: "即将毕业或刚毕业，在找工作",
    salaryTip: "谈薪时要问清楚：税前还是到手？五险一金按什么基数缴？绩效占比多少？试用期打几折？",
    recommendedSlugs: ["labor-contract-must-have", "five-insurance-one-fund", "probation-period", "intern-and-contracts"],
    homeTips: [
      "三方协议 ≠ 劳动合同，入职后必须另签劳动合同",
      "试用期最长6个月，工资不低于约定工资的80%",
      "试用期也必须缴社保，\"转正后补缴\"是违法的",
      "签合同前用AI帮你审查，找出隐患条款",
    ],
  },
  junior: {
    code: "junior",
    label: "职场新人",
    icon: "💼",
    description: "工作1~3年，刚步入正轨",
    salaryTip: "开始关注总包（年包）而不只是月薪。公积金、补贴、年终奖都是收入的一部分。",
    recommendedSlugs: ["five-insurance-one-fund", "salary-structure", "six-insurance-one-fund", "city-insurance-comparison"],
    homeTips: [
      "第一笔工资到手后，先建立应急基金（3~6个月生活费）",
      "公积金是强制储蓄，买房/租房/离职时可以提取",
      "每年关注专项附加扣除，可以少缴个税",
      "工资条要保存好，是维权的重要证据",
    ],
  },
  senior: {
    code: "senior",
    label: "稳定发展",
    icon: "🏠",
    description: "工作3~5年+，考虑长期规划",
    salaryTip: "关注年终奖计税方式（单独 vs 合并），可能差几千块。公积金余额可以考虑买房或提取。",
    recommendedSlugs: ["non-compete", "salary-structure", "six-insurance-one-fund"],
    homeTips: [
      "年终奖可以选择单独计税或并入综合所得，算算哪个更省",
      "公积金缴满一定年限后，贷款额度会更高",
      "如果考虑换城市，提前了解社保转移流程",
      "应急基金攒够后，可以考虑基金定投等理财方式",
    ],
  },
  experienced: {
    code: "experienced",
    label: "看新机会",
    icon: "🔍",
    description: "考虑跳槽或已在看新机会",
    salaryTip: "跳槽谈薪时关注总包（年包），对比时要扣除生活成本差异。别忽略竞业限制和社保断缴风险。",
    recommendedSlugs: ["non-compete", "salary-structure", "city-insurance-comparison"],
    homeTips: [
      "跳槽前确认：竞业限制范围、社保断缴影响、年假折算",
      "新offer的五险一金基数可能不同，到手工资会变化",
      "跳槽涨薪30%是常见预期，但要综合评估总包",
      "离职时记得提取公积金（部分城市离职后可全额提取）",
    ],
  },
};

const currentIdentity = ref(localStorage.getItem(STORAGE_KEY) || "");

function setIdentity(code) {
  if (IDENTITY_OPTIONS[code]) {
    currentIdentity.value = code;
    localStorage.setItem(STORAGE_KEY, code);
  }
}

function clearIdentity() {
  currentIdentity.value = "";
  localStorage.removeItem(STORAGE_KEY);
}

const identityConfig = computed(() => {
  if (!currentIdentity.value || !IDENTITY_OPTIONS[currentIdentity.value]) return null;
  return IDENTITY_OPTIONS[currentIdentity.value];
});

const isIdentitySet = computed(() => Boolean(currentIdentity.value && IDENTITY_OPTIONS[currentIdentity.value]));

export function useIdentity() {
  return {
    currentIdentity,
    identityConfig,
    isIdentitySet,
    identityOptions: IDENTITY_OPTIONS,
    setIdentity,
    clearIdentity,
  };
}
