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
| `market_core` | 通过显式清洗/质量门的标准岗位 | core transformer | 市场只读服务 |

三个 Alembic 迁移必须使用三个显式数据库 URL，不存在隐式共享默认值。MySQL 角色只按域授权，Guardian API 和市场只读角色不获得 staging/raw 权限。

## 适配器协议

- API、HTML、Playwright 适配器都将来源快照转为同一 `RawRecordInput`。
- 适配器不接收 Core Session，不调用标准岗位写入。
- Raw 按“数据源 + 规范内容 SHA-256”去重，保留首次/最后发现时间。
- Core 只有显式晋级入口，每条岗位同事务写入 `job_source`。
- 真实采集必须同时满足条款已确认、来源已启用、HTTPS 主机 allowlist、限速、超时与重试约束。

## 不复用的 Pin 设计

- 采集结果经 LLM 后直接写入标准岗位表。
- 站点代码、本地临时文件、任务状态和 Core 写入共用同一进程/数据库权限。
- 在源码中保存 Cookie，或将备份存放到 Git。

## 后续边界

FP-02 只建立 Raw 生产与来源回链骨架。岗位族、城市、技能、薪资和时效标准化以及质量门属于 FP-03。
