# 职护文档索引

> 目的：让新会话和后续开发只从少数权威入口开始，避免早期计划、历史验收和当前实现互相误导。

## 新会话先读

1. [仓库 README](../../README.md)：产品定位、仓库结构和运行时边界。
2. [当前进度与交接](../progress/PROGRESS.md)：稳定基线、未完成紧急 WIP、强制接手顺序和验收标准。新会话必须先完成其中第 0 节，不先开新功能。
3. [开发基线](./development.md)：本地环境、启动和基础验证。

## 当前产品与业务边界

- [职护 V2 产品蓝图](../docx/职护%20V2%20产品蓝图.md)：五域产品定位和目标体验。
- [决策守护当前实现](./decision-guardian.md)：外部 Offer 录入、比较与跨域流转边界。
- [职护 AI 配置说明](./ai-configuration.md)：管理员配置、密钥、模型、日志和降级边界。

## 当前数据与采集架构

- [职护当前数据库结构](./data/current-database-architecture.md)：MySQL 逻辑库、表职责和合法数据流。
- [招聘数据采集完整链路](./data/recruitment-collection-pipeline.md)：公司/渠道、浏览器、加载、增量、Raw、清洗、质量门、Core 和后台观测。
- [岗位质量门](./data/job-quality-gate.md)：可配置准入、版本与审核。
- [采集解析规则恢复与自愈](./data/collection-rule-self-healing.md)：故障分类、AI 候选、回放、审批和回滚。
- [Pin 历史数据质量报告](./data/pin-legacy-quality-report.md)：只读迁移与质量参考，不是当前运行说明。

## 架构与契约

- [`adr/`](./adr/)：关键架构决策记录。
- [`contracts/`](./contracts/)：跨服务与前后端契约。
- [统一领域模型](./domain-model.md)：职业事件、证据、结论与行动模型。
- [开发基线](./development.md) 与 ADR：权限、敏感数据、服务边界和本地安全约束。

## 历史资料

- [`acceptance/`](./acceptance/)：FP 阶段历史验收快照，用于追溯，不代表当前动态状态。
- [职护 V2 开发计划](../docx/职护%20V2%20开发计划.md)：历史执行计划；当前执行以进度交接文档为准。
- [职护产品需求文档 PRD](../docx/职护%20产品需求文档%20PRD.md)：早期 v0.2 产品规划；当前产品定义以 V2 蓝图为准。
- [`Reference/`](../Reference/) 与 [`Pin/`](../../Pin/)：历史来源和参考实现，职护运行时不得依赖。

## 已清理的过时入口

- `zhihu/QWEN.md`：旧 Windows 路径、旧 Sprint 规则和已失效执行说明。
- `zhihu/zhihu-frontend/CLAUDE.md`：仅转引不存在的局部说明，没有独立价值。
- `zhihu/zhihu-frontend/README.md` 的 Next.js 模板内容：已替换为本项目实际说明。
- `data/first-live-source-candidate.md`：一次性候选渠道调研，已被当前公司/渠道治理和历史验收取代。

## 事实优先级

若文档之间冲突：

```text
运行代码 / 数据库迁移 / 接口事实
  > 当前架构与治理文档
  > 当前进度交接
  > 历史验收
  > 早期开发计划与 PRD
  > 参考项目说明
```

动态数量、任务状态、AI 用量和渠道健康必须查询当前系统，不复制文档快照。
