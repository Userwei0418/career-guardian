"use client";

import { useState, useRef } from "react";
import { useArticleDrawer } from "@/context/ArticleContext";

// 术语 → 文章 slug + 简述
const TERM_MAP: Record<string, { slug: string; tip: string }> = {
  // 五险一金
  "五险一金": { slug: "wuxianyijin", tip: "养老、医疗、失业、工伤、生育保险 + 住房公积金，个人和公司共同缴纳" },
  "社保": { slug: "wuxianyijin", tip: "社会保险的简称，包含五险，是国家强制的社会保障制度" },
  "公积金": { slug: "gongjijin-xiangjie", tip: "个人和公司各缴 5%~12%，双边入账全部归你，可贷款买房利率更低" },
  "养老保险": { slug: "wuxianyijin", tip: "个人缴 8%，公司缴 16%，退休后按月领取养老金" },
  "医疗保险": { slug: "yibao-tuixiu", tip: "个人缴 2%，公司缴 ~10%，看病时可报销大部分费用" },
  "失业保险": { slug: "wuxianyijin", tip: "个人缴 0.2~0.5%，被辞退后可领取失业金（通常 2 年）" },
  "工伤保险": { slug: "wuxianyijin", tip: "个人不缴费，工作期间受伤可申请工伤认定和赔偿" },
  "生育保险": { slug: "wuxianyijin", tip: "个人不缴费，生育可报销医疗费并领取生育津贴" },
  // 养老金
  "养老金": { slug: "yanglaojin", tip: "退休后按月领取的养老金 = 基础养老金 + 个人账户养老金" },
  "基础养老金": { slug: "yanglaojin", tip: "由社平工资、缴费指数和缴费年限决定，体现'多缴多得、长缴多得'" },
  "个人账户养老金": { slug: "yanglaojin", tip: "个人账户累计额 ÷ 计发月数，60岁退休除以139" },
  "替代率": { slug: "yanglaojin", tip: "养老金 ÷ 退休前工资 × 100%，国际劳工组织建议 55% 以上" },
  "回本周期": { slug: "yanglaojin", tip: "个人缴纳总额 ÷ 年养老金，即多少年能'赚回'自己缴的钱" },
  "计发月数": { slug: "yanglaojin", tip: "退休年龄对应的除数：60岁=139月，55岁=170月，50岁=195月" },
  "记账利率": { slug: "yanglaojin", tip: "养老金个人账户每年的'利息'，目前约 3%，由国家统一公布" },
  "社平工资": { slug: "yanglaojin", tip: "当地上年度在岗职工月平均工资，每年公布，直接影响养老金计算" },
  "缴费指数": { slug: "yanglaojin", tip: "你的缴费基数 ÷ 社平工资，范围 0.6~3，越高退休金越多" },
  "缴费年限": { slug: "yanglaojin", tip: "缴纳社保的总年数，养老最低 15→20 年，医保各地 15~30 年不等" },
  // 医保
  "医保": { slug: "yibao-tuixiu", tip: "医疗保险，用于看病报销，退休后报销比例更高" },
  "报销比例": { slug: "yibao-tuixiu", tip: "医疗费用中医保承担的比例，在职约 70~85%，退休约 85~95%" },
  "最低缴费年限": { slug: "yibao-tuixiu", tip: "享受退休医保待遇需要缴满的最低年限，各地不同（15~30年）" },
  "个人账户": { slug: "yibao-tuixiu", tip: "医保个人账户，每月划入一笔钱，可用于门诊和药店购药" },
  // 补充保险
  "补充公积金": { slug: "buchong-gongjijin", tip: "企业在法定公积金之外额外缴纳 1~5%，全部归个人所有" },
  "补充医疗保险": { slug: "buchong-yiliaoxian", tip: "企业购买的商业保险，报销基本医保不覆盖的自费药、门诊等" },
  "六险一金": { slug: "buchong-yiliaoxian", tip: "五险一金 + 补充医疗保险，多出来的是公司额外买的商业医疗险" },
  // 薪资相关
  "年终奖": { slug: "nianzhongshui", tip: "可以单独计税或合并计税，选对了能省几千到几万" },
  "单独计税": { slug: "nianzhongshui", tip: "年终奖不并入工资，单独按月度税率表计算，适用于高薪" },
  "合并计税": { slug: "nianzhongshui", tip: "年终奖并入全年收入一起算税，适用于低薪或年终奖较少" },
  "社保基数": { slug: "shebao-jishu", tip: "计算五险一金缴纳金额的基数，通常是税前工资，有上下限" },
  "缴费基数": { slug: "shebao-jishu", tip: "同社保基数，决定每月缴纳多少五险一金" },
  "专项附加扣除": { slug: "zhuangjia-kouchu", tip: "子女教育、房贷、赡养老人等 7 项可从应纳税额中扣除" },
  "税前工资": { slug: "shuiqian-shoudao", tip: "合同约定的工资总额，扣除五险一金和个税后才是到手工资" },
  "税前月薪": { slug: "shuiqian-shoudao", tip: "同税前工资，即每月的基本薪资" },
  "税前总收入": { slug: "shuiqian-shoudao", tip: "基本月薪 + 绩效 + 补贴，五险一金和个税的计算基础" },
  "到手工资": { slug: "shuiqian-shoudao", tip: "实际打到银行卡的金额 = 税前 - 五险一金 - 个税" },
  "月到手": { slug: "shuiqian-shoudao", tip: "同到手工资，每月实际到账金额" },
  "年到手": { slug: "zhenshi-nianbao", tip: "月到手 × 12 + 年终奖到手" },
  "实发工资": { slug: "shuiqian-shoudao", tip: "同到手工资，工资条上'实发'栏的金额" },
  "应发工资": { slug: "shuiqian-shoudao", tip: "工资条上的税前总额，扣除五险一金和个税前的金额" },
  "基本月薪": { slug: "shuiqian-shoudao", tip: "合同约定的固定月薪，不含绩效和补贴" },
  "固定年收入": { slug: "zhenshi-nianbao", tip: "固定月薪 × 发薪月数，不含绩效和年终奖" },
  "真实年包": { slug: "zhenshi-nianbao", tip: "年到手 + 公积金双边年入，比表面年薪更能反映真实收入" },
  "双边缴存": { slug: "gongjijin-xiangjie", tip: "公积金个人缴一部分 + 公司等额匹配，两部分都归个人" },
  "提取": { slug: "gongjijin-tiqu", tip: "将公积金账户余额取出使用，租房/购房/离职/退休均可" },
  "补贴津贴": { slug: "butie-jintie", tip: "餐补、交通、住房、通讯等福利，计入税前收入参与五险一金和个税计算" },
  "补贴": { slug: "butie-jintie", tip: "同补贴津贴，公司额外发放的福利性收入" },
  // 个税
  "个税": { slug: "gerensuodeshui", tip: "个人所得税，起征点 5000 元/月，超出部分按 3%~45% 七级累进税率" },
  "个人所得税": { slug: "gerensuodeshui", tip: "同个税，起征点 5000 元/月，超出部分按 3%~45% 七级累进税率" },
  "起征点": { slug: "gerensuodeshui", tip: "每月 5000 元（年 6 万），工资扣除五险一金后不超过 5000 就不用交个税" },
  // 基础概念
  "试用期": { slug: "wuxianyijin", tip: "最长 6 个月（合同 3 年以上），工资不低于转正的 80%" },
  "绩效工资": { slug: "shuiqian-shoudao", tip: "根据考核结果浮动的工资部分，和固定工资一起构成月薪" },
  "储蓄率": { slug: "shuiqian-shoudao", tip: "月结余 ÷ 月到手 × 100%，反映你的存钱能力" },
};

export default function TermTooltip({ term, children }: { term: string; children?: React.ReactNode }) {
  const [show, setShow] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { openArticle } = useArticleDrawer();

  const info = TERM_MAP[term];
  if (!info) return <span>{children || term}</span>;

  const handleEnter = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setShow(true);
  };

  const handleLeave = () => {
    timerRef.current = setTimeout(() => setShow(false), 200);
  };

  return (
    <span className="relative inline-flex items-center gap-0.5">
      <span>{children || term}</span>
      <span
        className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-[var(--color-bg-warm)] text-[10px] text-[var(--color-text-muted)] cursor-help hover:bg-[var(--color-primary-light)] hover:text-[var(--color-primary)] transition-colors"
        onMouseEnter={handleEnter}
        onMouseLeave={handleLeave}
      >
        ?
      </span>

      {show && (
        <span
          className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 rounded-xl bg-white shadow-lg border border-[var(--color-border-light)] z-50 block"
          onMouseEnter={handleEnter}
          onMouseLeave={handleLeave}
        >
          <span className="text-xs text-[var(--color-text-secondary)] leading-relaxed mb-2 block">{info.tip}</span>
          <span
            onClick={() => { openArticle(info.slug); setShow(false); }}
            className="flex items-center gap-1 text-xs text-[var(--color-primary)] hover:underline font-medium cursor-pointer"
          >
            了解更多 <span>→</span>
          </span>
          <span className="absolute top-full left-1/2 -translate-x-1/2 w-2 h-2 bg-white border-r border-b border-[var(--color-border-light)] transform rotate-45 -mt-1 block" />
        </span>
      )}
    </span>
  );
}
