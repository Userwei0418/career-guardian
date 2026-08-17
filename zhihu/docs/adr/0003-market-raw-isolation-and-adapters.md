# ADR-0003：市场数据三域隔离与适配器边界

- 状态：Accepted
- 日期：2026-08-15
- 对应功能点：FP-02

## 决策

职护不直接合并 Pin 的后端和数据库，只选择性复用其结构化 API、HTML 和 Playwright 站点获取经验。新链路分为三个独立数据域：

| 数据域 | 职责 | 允许的写入者 | 业务查询 |
|---|---|---|---|
| `pin_legacy_staging` | 历史备份审计和授权迁移 | staging importer | 禁止 |
| `market_raw` | 数据源、任务、日志和原始快照 | crawler worker | 禁止 |
| `zhihu.market_*` | 通过显式清洗/质量门的标准岗位，与产品主库统一 | core transformer | 市场只读服务 |

三个 Alembic 迁移域分别作用于 `pin_legacy_staging`、`market_raw` 和 `zhihu.market_*`。Core 是逻辑事实层，不是独立数据库；`MARKET_CORE_DATABASE_URL` 必须指向 `zhihu`。MySQL 角色只按域授权，Guardian API 和市场只读角色不获得 staging/raw 权限。

## 适配器协议

- API、HTML、Playwright 适配器都将来源快照转为同一 `RawRecordInput`。
- 适配器不接收 Core Session，不调用标准岗位写入。
- Raw 按“数据源 + 规范内容 SHA-256”去重，保留首次/最后发现时间。
- Core 只有显式晋级入口，每条岗位同事务写入 `job_source`。
- 真实采集必须同时满足条款已确认、来源已启用、HTTPS 主机 allowlist、限速、超时与重试约束。
- 站点、分页、请求字段、产品字段映射和审批状态统一保存在 `market_raw`；注册表不得覆盖人工治理字段。
- Guardian API 只做代理和管理员权限校验；实际采集由独立 `market-data` worker 排队执行，用户请求不运行爬虫。

## 不复用的 Pin 设计

- 采集结果经 LLM 后直接写入标准岗位表。
- 站点代码、本地临时文件、任务状态和 Core 写入共用同一进程/数据库权限。
- 在源码中保存 Cookie，或将备份存放到 Git。

## Pin 站点配置迁移口径

Pin 的 `crawl_companies` 是历史候选目录，不等于可运行来源目录。迁移时按以下顺序处理：
1. URL 归一化和公司/站点去重；
2. 剔除非 HTTPS、失效地址和依赖旧 Cookie/本机文件的配置；
3. 转换成 API、HTML 或 Playwright 适配器配置；
4. 补齐分页上限、限速、字段映射和来源回链；
5. 以 `pending + disabled` 写入新库，等待管理员审核。

任何候选都不能因为来自旧 SQL 就自动获得审批或绕过质量门。

## 运行时收口（2026-08-17）

历史公司配置已转换为职护仓库内的版本化渠道目录和兼容解析资产。MySQL 初始化只读取这些职护资产；在线采集统一使用 `company_channel` 适配器及平台语义规则，不 import 旧项目代码，不读取旧项目配置目录，也不调用旧服务。旧项目路径只允许出现在历史审计和一次性备份重放工具中。

解析规则故障的后续治理遵循 [`采集解析规则自愈设计`](../data/collection-rule-self-healing.md)：AI 只能生成候选规则，必须经过脱敏快照回放、质量预检、canary 和可回滚发布后才能替换 active 版本。

## 当前进展

FP-02 最初只建立 Raw 生产与来源回链骨架。2026-08-17 已补齐来源审批审计、后台启停、后台任务、结构化 API 安全分页，以及部门、学历、经验、职责、专业等完整字段的 Raw→Core 保留。持续真实采集仍受来源审批边界约束。
