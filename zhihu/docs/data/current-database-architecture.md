# 职护当前数据库结构

- 生效日期：2026-08-16
- 状态：当前运行基线
- 适用范围：本仓库后续开发、迁移、采集和数据验收

## 唯一有效结构

职护当前只使用同一个 MySQL 实例中的三个数据库：

```text
zhihu（产品主库）
├── 用户、档案与个人材料版本
│   ├── users / user_profiles
│   ├── resume_versions
│   ├── personal_attachment_versions
│   ├── job_targets
│   ├── resume_tailoring_drafts
│   └── mock_interview_sessions
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
├── Offer 决策记录
│   ├── offers / offer_comparisons
│   └── HR 回复作为 decision 事件的私有 evidence
├── AI 配置与调用审计
│   ├── ai_provider_settings / ai_configuration_audits
│   └── ai_invocation_logs
└── Offer、合同、工资与知识等产品数据

market_raw（以后新采集的工程原文库）
├── recruitment_companies（招聘公司主体）
├── data_sources（公司招聘渠道、入口、字段映射、审批与启停）
├── collection_templates（招聘平台共用采集模板）
├── crawl_batches（公司级采集批次）
├── crawl_tasks / crawl_log_entries（渠道任务与运行日志）
└── raw_records

pin_legacy_staging（Pin 历史迁移证据库）
├── legacy_import_batches / legacy_table_stats
├── legacy_company_records / legacy_job_records
├── legacy_job_source_records
└── legacy_raw_records
```

`pin_legacy_staging` 是当前准确库名，不是 `market_staging`。它只服务 Pin 历史备份的重放、重洗和来源追溯；以后新抓取的数据直接进入 `market_raw`，不会写入该历史库。

`job_targets` 保存用户对通过质量门岗位的意向及岗位快照：`saved` 表示稍后比较，`target` 表示准备投入行动，并可绑定一份本人简历。目标岗位卡片上的简短建议不是前端临时文案，而由 `advice_kind`、`advice_summary`、`advice_source_analysis_id` 和 `advice_updated_at` 持久保存；它绑定产生建议的统一岗位分析，重新分析后更新，切换简历时不会沿用另一版本的旧建议。`resume_tailoring_drafts` 保存针对目标 JD 生成、但尚未确认的简历文字补丁；只有用户确认后才会新增 `resume_versions` 版本。AI 微调版本通过 `parent_resume_version_id`、`creation_source=ai_tailored` 和 `source_job_id` 保留来源链，不覆盖原版本，也不伪造原始附件。

机会页的岗位推荐只对 `zhihu.market_jobs` 中已通过数据准入的岗位建立候选池，先按用户选择的方向、专业、城市和招聘类型召回，再结合工作经验与学历门槛、岗位信息完整度，以及当前简历/档案中的已确认能力证据重排。新增抓取数据只有在通过统一质量门并进入 `market_jobs` 后，才会自动进入后续推荐池。相关度用于缩小检索范围，不表示录用概率；个人能力差距只在用户选定具体目标岗位并绑定简历后分析，不在市场首页做脱离目标的泛化判断。

`knowledge_articles` 保存职护知识正文。机会页先限制在求职和在校场景，再根据当前方向、专业、招聘类型及“岗位、JD、投递”等场景信号，对标题、标签、关键词和摘要做加权相关度排序；不会再按文章原始顺序混入养老、医保等无关内容。当前库随迁移提供 31 篇文章，其中 4 篇专门覆盖岗位真实性、JD 阅读、校招/实习选择和岗位清单管理。

目标岗位的能力路线与简历微调不再依赖单个页面里的临时 `loading`。`job_targets.plan_status` 记录路线任务的排队、执行、成功或失败状态；`resume_tailoring_drafts` 会在调用 AI 前先写入 `generating` 草稿，再保存完成结果或失败原因。前端按这些服务端状态轮询，因此切换页面不会取消任务，回来后可以继续看进度或重新打开最近草稿。已经生成的路线和草稿都是用户可收起、可复查的持久结果；关闭模态框不会删除草稿。`job_targets.plan_audio*` 使用“摘要 + TTS 模型 + 音色 + 语速等合成参数”的哈希缓存私有语音，任一输入变化时自动失效，不新建第四个文件库。

`mock_interview_sessions` 只服务用户已设定的目标岗位，并绑定当时使用的简历版本。它保存场次类型、难度、时长、模型/音色、状态、结构化逐字稿、摘要和复盘；逐字稿逐条保留 `sequence`、`role`、`text`，供复盘生成与用户回看。实时通话中的 PCM 音频只做转发和即时播放，不写文件、不写数据库；即使复盘模型失败，已经收到的逐字稿也会先落库。

`ai_provider_settings` 由管理员统一保存文本、TTS 和实时对话模型配置，密钥只保存加密文和末四位。`ai_invocation_logs` 按用户、功能点、能力类型、时间、耗时、用量和成功/失败状态记录调用；能力类型统一为 `text` / `audio` / `image` / `video` / `realtime`，不保存请求或回复正文。

`offers` 是决策守护的业务档案，不是一次向导的临时状态。它保存用户从外部招聘流程获得的书面/口头 Offer、回复期限、关联原始附件版本和 `evaluating` / `on_hold` / `accepted` / `declined` / `expired` 决定状态。机会守护不承担真实招聘或投递，因此收藏/目标岗位不会自动生成 Offer，目标岗位卡片也不提供“记录 Offer”入口；`job_target_id` 仅作为既有数据兼容字段保留。`offer_comparisons` 保存两份库存 Offer 在当时的事实快照、偏好快照、估算假设和条件化比较结果；Offer 后续修改不会篡改历史比较。

用户每次确认接受、拒绝或暂缓时，理由写入对应 decision 事件的 `decision_records`，旧记录不被覆盖。暂缓会在原事件创建带复盘时间的 `action_items`。接受 Offer 只会为同一用户幂等建立三项后续职业事件：权益守护的合同承诺核对、收入守护的首份工资一致性核对、成长守护的入职 30 天任务；这些记录是待办，不代表合同、工资或入职事实已经发生。用户之后修正为拒绝或暂缓时，既有后续事件会归档而不会静默删除历史。

岗位列表的“初筛相关度”和岗位详情的“综合证据匹配度”使用同一套 `resume-job-fit-v3` 证据口径：方向相关性 35 分、学历/专业/经验等背景硬条件 30 分、简历已确认技能证据 35 分。专业匹配只读取简历结构化教育经历或明确的教育/专业行，不会因项目正文中的普通同名词误判。详情分析把计分版本和分项保存在 `opportunity_analyses.scoring_version`、`score_breakdown`；AI 只解释优势、缺口和行动建议，不能改写分数。简历微调沿用这份分析结果，只优化已有事实的表达，不另算一套分数。存在明确经验、学历或专业硬门槛未满足时，即使技能文字全部命中也不会显示为 100%。

用户上传原件不建第四个数据库。`personal_attachment_versions` 保存所有个人附件的类型、逻辑组、版本号、原文件名、类型、大小、哈希和私有存储引用；二进制原件落在服务端 `UPLOAD_DIR/personal/<user_id>/...`。`resume_versions` 保存简历解析全文、结构化档案、AI 解析模式/模型与对应原件版本引用。

个人附件版本规则：

1. 每次文件上传都新建版本，即使文件内容相同也不覆盖旧版。
2. 简历的当前版本由 `resume_versions.is_active` 明确选择；JD 匹配使用指定版本的结构化档案和解析全文，技能标签只作索引。
3. 前端不获得存储路径；查看/下载必须通过所有权校验接口。
4. 清空用户数据或删除账号时，同步删除附件数据库记录与原件。
5. 2026-08-16 之前的旧简历上传没有保留原件，只能补解析现存全文；用户重新上传后才能建立原件版本。

目前还没有独立的“岗位申请状态”表。`job_targets` 只表达收藏和目标，不代表已经投递；岗位守护、下一步动作和结果分别记录在 `career_events`、`action_items` 和 `outcomes`。如果后续要追踪“已投递、笔试、面试、Offer、拒绝”等申请流水，应新建明确的申请实体，不能把现有意向或行动状态误称为完整 ATS。

## 两条合法入库路径

```text
Pin 历史备份
  → pin_legacy_staging
  → 字段映射 + 统一质量门 + 去重
  → zhihu.market_*

以后新抓取
  → market_raw
  → 来源字段映射 + 血缘校验 + 统一质量门 + 去重
  → zhihu.market_*
```

用户页面和市场洞察服务只读 `zhihu.market_*`。它们不得读取 Raw 或 Staging，也不得把未通过质量门的候选记录直接展示给用户。

管理员启动公司采集前，其中的招聘渠道必须同时具备配置校验通过、条款审批、启用状态、HTTPS 白名单和 `promotion_mapping` 产品字段映射。采集成功后，本次新 Raw 会自动进入映射与质量门：通过项标记 `promoted` 并写入 `zhihu.market_*`，不通过项标记 `quarantined` 并保存原因码。只有 `promoted` 才算进入产品库；异常中断时保留 `pending_gate` 供排查和重试，绝不把它当作合格岗位。

`market-data` 是独立采集服务，不在职护页面请求中同步执行爬虫。管理员操作由 Guardian API 鉴权后代理到内部管理接口，任务进入 `pending` 后由采集 worker 执行；页面按任务状态轮询。来源注册表只负责首次初始化；之后来源名称、适配器、入口、域名白名单、分页、限速、超时、重试、字段映射与人工审批均以 `market_raw.data_sources` 为准，服务重启不会覆盖管理员修改。

管理后台按“公司招聘渠道 → Raw 留痕 → 标准化与去重 → 质量门 → 主库”展示完整流程。公司是管理员的主要操作对象，校招、实习和社招等渠道收在公司详情内；平台模板复用 Moka、飞书、北森、HotJob 等共用抓取逻辑。每个历史任务固化读取数、Raw 新增数、重复数、晋级数、隔离数和失败数，不依赖前端临时计算。Cookie、Token、密钥和密码会被服务端拒绝保存。

2026-08-17 当前快照：`zhihu` 有 132,845 条标准岗位、132,846 条岗位来源和 554 家标准企业；`market_raw` 有 631 家采集公司、1,470 个公司招聘渠道、4 个开发/原生验证来源和 8 类采集模板，其中 1,467 个历史渠道已经转为职护自有 `company_channel` 适配器，日常运行不再读取旧项目。98 个渠道因非 HTTPS、入口缺失、缺少安全解析规则，或原兼容脚本含网络请求/历史凭据而被标为配置异常，不会自动运行。三安光电的校园、社会和专项渠道已完成一次真实采集验证：Raw 42 条、晋级来源 42 条、形成 41 条新标准岗位、隔离 0 条。历史岗位数据仍完整保留在 `pin_legacy_staging`，后续实时数量以管理后台为准。

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
5. 原始个人附件不得放入公开静态目录或 Git；备份和恢复时必须同时处理 `zhihu.personal_attachment_versions` 与 `UPLOAD_DIR`。
6. 统计“岗位数量”使用 `market_jobs` 或 `legacy_job_records`，不得把 Raw、来源和技能关系行相加。
7. 文档、环境示例和启动脚本不得再把 `market_core` 描述为独立数据库。
