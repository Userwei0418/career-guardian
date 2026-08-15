# 职护当前数据库结构

- 生效日期：2026-08-15
- 状态：当前运行基线
- 适用范围：本仓库后续开发、迁移、采集和数据验收

## 唯一有效结构

职护当前只使用同一个 MySQL 实例中的三个数据库：

```text
zhihu（产品主库）
├── 用户、档案与简历版本
│   ├── users / user_profiles
│   └── resume_versions
├── 清洗后的市场事实
│   ├── market_jobs / market_job_sources
│   ├── market_companies / market_cities
│   ├── market_job_families / market_recruitment_types
│   ├── market_skills / market_job_skills
│   └── market_insight_snapshots
├── 质量门配置与迁移审计
│   ├── market_quality_gate_policies
│   ├── market_core_promotion_batches
│   └── market_rejected_legacy_jobs
├── 五域守护记录
│   ├── career_events / evidence / guardian_findings
│   ├── action_items / decision_records / outcomes
│   └── opportunity_analyses
└── Offer、合同、工资与知识等产品数据

market_raw（以后新采集的工程原文库）
├── data_sources
├── crawl_tasks / crawl_log_entries
└── raw_records

pin_legacy_staging（Pin 历史迁移证据库）
├── legacy_import_batches / legacy_table_stats
├── legacy_company_records / legacy_job_records
├── legacy_job_source_records
└── legacy_raw_records
```

`pin_legacy_staging` 是当前准确库名，不是 `market_staging`。它只服务 Pin 历史备份的重放、重洗和来源追溯；以后新抓取的数据直接进入 `market_raw`，不会写入该历史库。

目前还没有独立的“岗位申请状态”表。岗位守护、下一步动作和结果分别记录在 `career_events`、`action_items` 和 `outcomes`；如果后续要追踪“已投递、笔试、面试、Offer、拒绝”等申请流水，应新建明确的申请实体，不能把现有行动状态误称为完整 ATS。

## 两条合法入库路径

```text
Pin 历史备份
  → pin_legacy_staging
  → 字段映射 + 统一质量门 + 去重
  → zhihu.market_*

以后新抓取
  → market_raw
  → 来源适配 + 统一质量门 + 去重
  → zhihu.market_*
```

用户页面和市场洞察服务只读 `zhihu.market_*`。它们不得读取 Raw 或 Staging，也不得把未通过质量门的候选记录直接展示给用户。

2026-08-15 清理后的现场快照：`zhihu` 有 132,804 条标准岗位、132,804 条岗位来源、554 家企业、64 个标准城市、12 个岗位方向和 88,464 个技能标签；`market_raw` 有 5 个来源配置、0 个采集任务、0 条新 Raw；历史数据仍完整保留在 `pin_legacy_staging`。

## 存量数据为什么不是 30 万个岗位

Pin 备份中的岗位相关表是同一批事实的不同层次，不是可以相加的独立岗位：

| 备份/迁移记录 | 行数 | 含义 |
|---|---:|---|
| `jobs` / `legacy_job_records` | 133,657 | 岗位候选实体，是计算岗位总数的基准 |
| `raw_job_records` / `legacy_raw_records` | 133,656 | 与岗位对应的原始 JSON/内容哈希证据 |
| `job_sources` / `legacy_job_source_records` | 133,657 | 与岗位对应的来源 URL 和观察时间证据 |
| `companies` / `legacy_company_records` | 567 | 企业候选，不是岗位 |

因此，看到约 30 万甚至 40 万“岗位相关行”时，不能理解为同等数量的岗位。一次岗位通常同时贡献一条岗位行、一条 Raw 行和一条来源行。

正式质量门批次的最终结果：

| 处理结果 | 数量 | 说明 |
|---|---:|---|
| 进入 `zhihu.market_jobs` | 132,804 | 保留来源回链的标准岗位事实 |
| 重复候选 | 853 | 稳定身份键与已晋级岗位相同，不重复新建岗位 |
| 质量门隔离 | 0 | 本批没有岗位因硬条件失败而被整体删除 |
| 合计 | 133,657 | 与 Staging 岗位候选数完全一致 |

薪资、城市、技能等字段采用“字段降级”策略。例如只有 10,505 条记录具备可进入薪资统计的可靠薪资，但薪资缺失或异常不会删除对应岗位；这些岗位仍可用于岗位事实、职责和来源核对。

## 已删除的旧库

独立数据库 `market_core` 已于 2026-08-15 删除。删除前已经确认：

- 当前运行时无任何连接指向该库；
- 旧库与 `zhihu.market_*` 的岗位、来源、企业、技能、岗位技能关系及晋级批次数量一致；
- 当前配置把 `MARKET_CORE_DATABASE_URL` 固定派生为 `zhihu`。

后续不得重新创建或连接独立 `market_core` 数据库。代码中的 `Core` 仅表示“通过质量门的产品市场事实层”；物理存储位置始终是 `zhihu.market_*`。

## 开发约束

1. 新业务表默认进入 `zhihu`，除非它是不可变采集原文或历史迁移证据。
2. 新采集器只能写 `market_raw`，不能直接写 `zhihu.market_jobs`。
3. `pin_legacy_staging` 不接收未来常规采集数据。
4. 用户私有材料不得进入 `market_raw` 或 `pin_legacy_staging`。
5. 统计“岗位数量”使用 `market_jobs` 或 `legacy_job_records`，不得把 Raw、来源和技能关系行相加。
6. 文档、环境示例和启动脚本不得再把 `market_core` 描述为独立数据库。
