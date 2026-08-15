# 职护 — 开发进度记录

> 每个 Sprint 完成后更新，用于追溯和断点恢复。

---

## V2.1 集成开发（执行中）

**最后更新**：2026-08-15

### 产品主结构确认

- 一级业务结构固定为机会守护、决策守护、权益守护、收入守护、成长守护；`/today` 保留为个人首页，但不再作为并列业务导航。
- 五域页面是面向用户问题的完整工作台，职业事件、证据、结论、行动、决定和结果作为跨域底层机制，不替代领域产品本身。
- 机会守护采用用户侧与管理员侧双层结构：用户查看标准岗位、企业事实、市场图表和个人匹配；管理员管理数据源、采集任务、运行日志、质量门和标准数据晋级。
- `zhaogebanshang`/Pin 复用的是获取与解析能力，进入职护前仍需按岗位、企业、城市、薪资、技能、来源和时效重新清洗，采集结果不得直接进入个人结论。

### 已完成：阶段 1 共同连接点

- 五域导航、今天首页和机会/决策/权益/收入/成长状态骨架已进入 `main`。
- `CareerEvent → Evidence → GuardianFinding → ActionItem` 及决策、结果的统一模型和登录态 API 已可用。
- 市场洞察 API 已提供岗位、薪资分位和技能信号，并保留来源、时效、样本和方法元数据。
- Pin API 已有只读适配入口；默认运行脱敏 `fixture`，不启动真实采集。
- 机会守护页面可以查看有来源的岗位/薪资/技能事实，并把选中岗位写入职业事件、证据、结论和人工确认行动。

### 已完成：阶段 2 核心组装

- Offer 报告已停用内置 mock 分位，改用市场洞察契约，显示数据模式、分位、样本、质量、方法和来源。
- HR 实际回复可写入决策事件的私有证据，用户可将未解决问题加入待办。
- 合同规则审查、Offer—合同差异和签约清单已幂等写入权益结论和人工确认行动。
- 工资条可保存到职护业务库，优先与关联 Offer 应发金额核对，差额写入收入事件；私有工资数据不发送给市场服务。
- 成长守护已将公开市场技能和个人已确认技能分开存证，生成的行动保持为待用户确认的草稿。
- 首页可显式载入一个脱敏应届生连续案例；旅程页会按事件展示五域证据、结论和行动数。

### 已完成：阶段 3 事件交互闭环

- 首页和旅程中的非空守护状态已直接进入对应职业事件，不再只回到领域入口。
- 新增职业事件工作台，集中展示行动、结论、证据、决定和结果，并明确公共市场事实、私有材料、规则、计算和 AI 辅助来源。
- 用户可以确认行动草稿、标记行动完成、确认或解决结论，并在待办清零后关闭事件；关闭后首页会自动选择下一项首要守护任务。
- 需要人工确认的行动在后端强制执行确认边界；仍有草稿或进行中行动时，后端拒绝关闭事件。
- 所有事件、行动和结论更新继续按登录用户隔离，其他账号不能修改。
- 决策、权益和收入三个一级入口已升级为材料驱动工作台：直接汇总 Offer、合同和工资条，并按同一记录进入报告、HR 回复、条款审查、承诺差异、签约清单或守护事件。
- Offer、合同和工资条下游页面已支持 URL 中的业务 ID，同时保留原本地流程状态作为兼容回退；从工作台和管理列表进入时不再依赖先走一遍旧向导。

### 已完成：候选版代码收口

- 清理了受控前端源码中的 React Hooks、未使用变量和显式 `any` 警告；登录失效跳转和知识抽屉状态更新也已按当前 Next/React 约束调整。
- 薪资保存记录和养老金、医保、公积金响应已补齐前端类型，减少计算页运行时字段漂移。
- 修复公积金提取规则的后端契约：实际返回的场景、条件、额度现在保持为结构化对象，并新增接口回归测试。
- 修复失效 JWT 的登录重定向循环：401 会同时清除 token 与持久登录状态，欢迎页只在有效 token 仍存在时进入首页。
- 职业事件关闭条件已补齐：草稿/进行中行动，或尚未确认的高优先级/警告结论，都会在前后端阻止事件被提前关闭。

### 当前验证证据

- 市场数据：21 个单元/契约测试通过，包括 Pin 响应映射和上游不可用降级。
- 职护后端：27 个安全、事件、迁移、市场网关、财务契约和连续案例测试通过。
- 职护前端：所有受控源码 ESLint 无警告；全库仅剩用户未跟踪 `today/page 2.tsx` 中的 3 条警告。Next.js 16.3.1 Webpack 生产构建通过，新增动态路由 `/events/[id]`。
- HTTP 完整旅程：脱敏岗位→Offer 市场位置→HR 回复→合同审查/差异/清单→工资差额→技能差距已经真实跨两个本地服务跑通。Offer 市场样本数 86；第二份工资条与 Offer 差 -500 元；首页主状态为收入需关注；成长差距返回 Python、数据可视化和统计学。
- HTTP 事件闭环：收入事件的行动确认、完成，结论解决和事件关闭均通过真实本地接口；关闭后首页主守护领域从收入自动转到成长。
- 浏览器主路径：在本地脱敏账号中完成登录、载入连续案例、首页进入收入事件、完成行动、解决结论、关闭事件、首页焦点转成长；并从决策/权益工作台通过 URL 业务 ID 直接进入 Offer 报告和合同审查。
- 响应式检查：1440×900 首页和 390×844 决策工作台均完成可见页面检查；移动端文档宽度与视口同为 390px，无横向溢出。

### 继续开发

- 清理重复入口和临时兼容层，统一空状态、错误状态与关键文案。
- 阶段 4 候选版验证：补齐浏览器及主要移动端路径，收敛旧页面警告和 P0 问题。

## Sprint 1 ✅ — 项目脚手架 + 设计系统 + 基础页面

**完成时间**：2026-07-17

### 后端（zhihu-backend/）

| 文件 | 说明 | 状态 |
|------|------|------|
| `app/main.py` | FastAPI 入口，注册 8 个路由模块 + CORS | ✅ |
| `app/core/config.py` | Pydantic Settings 配置（DB/Redis/JWT/LLM） | ✅ |
| `app/core/security.py` | JWT token + bcrypt 密码 | ✅ |
| `app/db/session.py` | SQLAlchemy 连接池 + Base + get_db | ✅ |
| `app/api/deps.py` | get_current_user 依赖注入 | ✅ |
| `app/models/user.py` | users 表 | ✅ |
| `app/models/user_profile.py` | user_profiles 表 | ✅ |
| `app/models/career_case.py` | career_cases 表 | ✅ |
| `app/models/offer.py` | offers 表（完整 Offer 字段 + confidence） | ✅ |
| `app/models/contract.py` | contracts 表 | ✅ |
| `app/models/finding.py` | findings 表（分析结论 + 溯源） | ✅ |
| `app/models/journey_node.py` | journey_nodes 表 | ✅ |
| `app/models/payslip.py` | payslips 表（P1） | ✅ |
| `app/api/routes/auth.py` | 登录/注册/演示模式/me | ✅ |
| `app/api/routes/health.py` | 健康检查 | ✅ |
| `app/api/routes/profiles.py` | 用户档案 CRUD | ✅ |
| `app/api/routes/cases.py` | 职场任务 CRUD | ✅ |
| `app/api/routes/offers.py` | Offer CRUD | ✅ |
| `app/api/routes/contracts.py` | 合同 CRUD | ✅ |
| `app/api/routes/findings.py` | 分析结论查询 | ✅ |
| `app/api/routes/journey.py` | 旅程查询 + 完成节点 | ✅ |
| `alembic/` | 迁移配置 + 初始建表脚本 | ✅ |
| `requirements.txt` | Python 依赖 | ✅ |
| `.env.example` | 环境变量模板 | ✅ |

### 前端（zhihu-frontend/）

| 文件 | 说明 | 状态 |
|------|------|------|
| `src/app/globals.css` | 职护设计系统（色彩/圆角/阴影/组件样式） | ✅ |
| `src/app/layout.tsx` | 根布局（zh-CN, metadata） | ✅ |
| `src/app/page.tsx` | 根页面 → redirect /welcome | ✅ |
| `src/app/welcome/page.tsx` | 欢迎页 + 情况选择 + 轻量问题（3 步） | ✅ |
| `src/app/(main)/layout.tsx` | 主布局（Navbar + 内容区） | ✅ |
| `src/app/(main)/today/page.tsx` | 陪伴式首页（问候/行动卡/快捷事件/时间线） | ✅ |
| `src/app/(main)/tasks/page.tsx` | 一起看看（自然语言输入 + 6 个入口） | ✅ |
| `src/app/(main)/journey/page.tsx` | 我的旅程（时间线骨架） | ✅ |
| `src/app/(main)/profile/page.tsx` | 我的档案（基本情况/隐私设置） | ✅ |
| `src/lib/api.ts` | 统一 API 调用层（fetchAPI 封装） | ✅ |
| `src/stores/auth.ts` | Zustand 认证状态（login/demo/register/logout） | ✅ |
| `src/components/layout/Navbar.tsx` | 顶部导航（4 个 tab + 演示模式标签） | ✅ |
| `src/components/ui/StepProgress.tsx` | 步骤进度条组件 | ✅ |

### Bug 修复

| 问题 | 修复 | 文件 |
|------|------|------|
| 演示模式按钮在后端不可用时崩溃 | loginDemo 添加 try/catch，降级为本地演示模式 | `src/stores/auth.ts` |
| SSR hydration mismatch（isLoggedIn 在服务端/客户端不一致） | 将重定向逻辑移入 useEffect | `src/app/welcome/page.tsx` |

### 启动方式

```bash
# 后端（需要 MySQL）
cd D:\code\zhihu\zhihu-backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端（可独立运行，后端不可用时演示模式自动降级为本地）
cd D:\code\zhihu\zhihu-frontend
npm install
npm run dev
# → http://localhost:3000
```

### 验证结果

- 前端 `npm run build` ✅ 通过，所有路由正常生成
- 前端 `npm run dev` ✅ 运行在 localhost:3000
- 演示模式 ✅ 无需后端即可浏览 UI
- 后端待验证（需要安装依赖 + 启动 uvicorn + MySQL）

---

## Sprint 2 ✅ — Offer 录入 + 信息确认 + 偏好设置

**完成时间**：2026-07-17

### 后端新增文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `app/schemas/offer.py` | Offer 请求/响应 Schema（OfferField 带 confidence、OfferExtractedFields） | ✅ |
| `app/schemas/profile.py` | 用户档案请求/响应 Schema | ✅ |
| `app/services/document_service.py` | 文档上传服务（PDF/图片 → PyMuPDF 文本提取 + 校验） | ✅ |
| `app/services/assistant_service.py` | AI 抽取服务（LLM 结构化抽取 + confidence + 降级 + mock 数据） | ✅ |
| `app/api/routes/documents.py` | 文档上传/粘贴/抽取 API + 演示 Offer 接口 | ✅ |
| `app/api/routes/offers.py` | 重写：使用 Pydantic Schema 的 Offer CRUD | ✅ |
| `app/api/routes/cases.py` | 重写：使用 Pydantic Schema 的 Case CRUD | ✅ |
| `app/api/routes/profiles.py` | 重写：使用 Pydantic Schema 的档案 API | ✅ |
| `app/main.py` | 注册 documents 路由 | ✅ |

### 前端新增文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `src/stores/offer.ts` | Zustand Offer 流程状态（字段数据/步骤/偏好） | ✅ |
| `src/app/(main)/offer/new/page.tsx` | Offer 材料提交页（上传/粘贴/手动三种方式） | ✅ |
| `src/app/(main)/offer/confirm/page.tsx` | Offer 信息确认页（分组卡片 + 置信度标记 + 字段编辑） | ✅ |
| `src/app/(main)/offer/preferences/page.tsx` | 个人偏好页（8 项因素选 3 + 补充信息） | ✅ |

### 修改文件

| 文件 | 改动 |
|------|------|
| `src/app/(main)/tasks/page.tsx` | 更新链接指向 /offer/new，未实现功能标注 Sprint 编号 |
| `src/app/(main)/today/page.tsx` | 快捷入口"我拿到 Offer 了"指向 /offer/new |

### 关键设计

- **AI 抽取**：LLM 输出约束为固定 JSON schema，每字段带 confidence + evidence_text
- **置信度标记**：confidence < 0.7 的字段显示浅橙边框 + "需要确认"标签
- **降级策略**：LLM 不可用时返回空结果，引导用户手动填写
- **演示数据**：`build_mock_offer()` 提供小林案例预填充数据

### 验证结果

- 前端 `npm run build` ✅ 通过，新增 3 个路由（/offer/new, /offer/confirm, /offer/preferences）
- 后端 `uvicorn app.main:app` ✅ 启动成功，`/api/health` 返回正常
- 后端 `/api/auth/demo` ✅ 演示模式登录返回 JWT token
- MySQL `zhihu` 库 ✅ 9 张表全部创建成功

### Bug 修复

| 问题 | 修复 | 文件 |
|------|------|------|
| Python 3.9 不支持 `str \| None` 语法 | 改为 `Optional[str]` | `security.py`, `deps.py`, `document_service.py`, `assistant_service.py`, `profiles.py` |
| Alembic 连接数据库密码错误 | alembic.ini 更新密码 + env.py 改为从 .env 读取 | `alembic.ini`, `alembic/env.py` |

### 已知问题

- 后端 document_service.py 中图片 OCR 仅支持 PyMuPDF 文本层，完整 OCR 需接入 Tesseract
- 前端上传接口直接调用 fetch（非 api 封装），因需 FormData 格式

---

## Sprint 3 ✅ — Offer 分析报告 + 对比 + 薪资计算

**完成时间**：2026-07-17

### 后端新增文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `app/services/calculator_service.py` | 薪资计算引擎（10 城市五险一金 + 个税累计预扣法 + 生活结余） | ✅ |
| `app/services/market_service.py` | 市场数据 mock（4 岗位 × 10 城市薪资分位数 + 百分位计算） | ✅ |
| `app/services/report_service.py` | Offer 分析报告生成 + HR 问题话术生成 | ✅ |
| `app/api/routes/reports.py` | 报告/HR话术/薪资计算/城市数据 API | ✅ |
| `app/main.py` | 注册 reports 路由 | ✅ |

### 前端新增文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `src/app/(main)/offer/report/page.tsx` | Offer 分析报告页（收入卡 + 五险一金明细 + 待确认事项 + 下一步） | ✅ |
| `src/app/(main)/offer/compare/page.tsx` | Offer 对比页（双栏输入 + 实时计算 + 条件化推荐） | ✅ |
| `src/app/(main)/salary/page.tsx` | 薪资与生活结余页（收入流向可视化 + 参数调整即时更新） | ✅ |
| `src/app/(main)/offer/hr-questions/page.tsx` | HR 问题与话术页（动态生成 + 一键复制 + 勾选确认） | ✅ |

### 关键数据

- **10 城市五险一金比例**：养老 8%、医疗 2%、失业 0.2-0.5%、公积金 5-12%
- **个税税率表**：7 级累进（3%-45%），速算扣除数
- **生活成本**：8 项支出分类（房租/餐饮/交通/水电/通讯/日用/娱乐/其他）
- **市场数据**：4 岗位（前端/后端/产品/数据分析）× 10 城市，含 P25/P50/P75

### 验证结果

- 前端 `npm run build` ✅ 通过，新增 4 个路由（/offer/report, /offer/compare, /salary, /offer/hr-questions）
- 总计 16 个路由全部正常

---

## Sprint 4 ✅ — 合同审查 + 一致性检查 + 签约清单

**完成时间**：2026-07-17

### 后端新增文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `app/services/contract_review_service.py` | 劳动合同审查规则引擎（8 条内置规则 + 评分 + 清单生成） | ✅ |
| `app/services/consistency_service.py` | Offer-合同一致性检查（薪资/地点/试用期/年终奖逐项对比） | ✅ |
| `app/api/routes/contracts.py` | 重写：合同 CRUD + 审查 + 一致性检查 + 清单 API | ✅ |

### 前端新增文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `src/app/(main)/contract/new/page.tsx` | 合同上传页（基本信息 + 粘贴合同内容） | ✅ |
| `src/app/(main)/contract/review/page.tsx` | 合同"说人话"阅读页（评分卡 + 风险项展开 + 原文定位） | ✅ |
| `src/app/(main)/contract/consistency/page.tsx` | Offer-合同一致性页（逐项对比卡片 + 状态标记） | ✅ |
| `src/app/(main)/checklist/page.tsx` | 签约前行动清单页（优先级排序 + 勾选 + 完成提示） | ✅ |

### 关键设计

- **8 条劳动合同内置规则**：试用期过长、试用期工资低、竞业限制无补偿、违约金、工作地点模糊、单方解除权、社保缺失、加班无补偿
- **风险评分**：100 分起扣（high -15, medium -8, low -3），映射 A-F 等级
- **一致性检查**：薪资/地点/试用期/年终奖/岗位 5 项对比，4 种状态（一致/表述不同/存在差异/合同中缺失）
- **文案规范**：不说"风险等级高"，说"这一条签之前一定要问清楚"

### 验证结果

- 前端 `npm run build` ✅ 通过，新增 4 个路由（/contract/new, /contract/review, /contract/consistency, /checklist）
- 总计 20 个路由全部正常
- 后端 API 待验证（需重启后端）

### Bug 修复

| 问题 | 修复 | 文件 |
|------|------|------|
| Pydantic Settings 不允许 .env 多余字段 | 添加 `extra = "ignore"` | `app/core/config.py` |

---

## Sprint 5 ✅ — 旅程系统 + 档案 + 工资条（P1）

**完成时间**：2026-07-17

### 后端新增文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `app/services/journey_service.py` | 旅程编排（9 节点模板 + 下一步推荐） | ✅ |
| `app/services/payslip_service.py` | 工资条解析与核对（数字校验 + 预期对比） | ✅ |
| `app/api/routes/payslips.py` | 工资条分析 API | ✅ |
| `app/api/routes/journey.py` | 重写：旅程查询 + 按标题完成节点 | ✅ |
| `app/main.py` | 注册 payslips 路由 | ✅ |

### 前端修改/新增文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `src/app/(main)/journey/page.tsx` | 重写：完整时间线 + 下一步推荐 + 节点链接 | ✅ |
| `src/app/(main)/profile/page.tsx` | 重写：可编辑档案（阶段/城市/岗位）+ 隐私设置 | ✅ |
| `src/app/(main)/payslip/page.tsx` | 工资条核对页（明细填写 + 数字校验 + 预期对比） | ✅ |

### 验证结果

- 前端 `npm run build` ✅ 通过，新增 1 个路由（/payslip），总计 21 个路由
- 后端 API 待验证（需重启后端）

---

## Sprint 6 ✅ — 前后端全面接通 + 打磨优化

**完成时间**：2026-07-17

### 核心工作：将所有前端页面从硬编码/mock 数据改为真实调用后端 API

### 基础设施改动

| 文件 | 说明 | 状态 |
|------|------|------|
| `src/lib/api.ts` | 新增 `api.upload()` 方法，支持 FormData 文件上传 | ✅ |
| `src/stores/offer.ts` | 增加 `zustand/middleware` persist 持久化到 localStorage；新增 `createCaseAndOffer()` 方法自动创建 case + offer | ✅ |
| `src/stores/contract.ts` | **新建** Zustand store，管理 contractId/linkedOfferId，带 localStorage 持久化 | ✅ |

### Offer 流程接通（Sprint 2-3 页面）

| 文件 | 改动 | 状态 |
|------|------|------|
| `offer/confirm/page.tsx` | 确认时调用 `createCaseAndOffer()` 创建后端记录，增加 loading/error 状态 | ✅ |
| `offer/preferences/page.tsx` | 保存偏好到 `PUT /api/profiles/`；修复跳转：`/today` → `/offer/report` | ✅ |
| `offer/report/page.tsx` | 重写为调用 `GET /api/reports/offer/{offerId}`，展示后端返回的收入概览、五险一金、市场分位、匹配分析、待确认事项 | ✅ |
| `offer/hr-questions/page.tsx` | 重写为调用 `GET /api/reports/offer/{offerId}/hr-questions`，用后端生成的话术替换前端硬编码 | ✅ |
| `offer/compare/page.tsx` | 薪资计算改为调用 `GET /api/reports/salary/calculate`（500ms debounce），保留本地计算作为降级 | ✅ |
| `offer/new/page.tsx` | 文件上传改用 `api.upload()` 替代原生 fetch | ✅ |

### 合同流程接通（Sprint 4 页面）

| 文件 | 改动 | 状态 |
|------|------|------|
| `contract/new/page.tsx` | 提交表单到 `POST /api/contracts/`，保存 contractId 到 contract store | ✅ |
| `contract/review/page.tsx` | 重写为调用 `POST /api/contracts/{contractId}/review`，用后端审查结果替换 mockFindings | ✅ |
| `contract/consistency/page.tsx` | 重写为调用 `POST /api/contracts/{contractId}/consistency`，用后端对比结果替换 mockDiffs | ✅ |
| `checklist/page.tsx` | 重写为调用 `POST /api/contracts/{contractId}/checklist`，用后端生成的清单替换硬编码 | ✅ |

### 档案 + 旅程接通（Sprint 5 页面）

| 文件 | 改动 | 状态 |
|------|------|------|
| `profile/page.tsx` | 页面加载时 `GET /api/profiles/` 回填表单；保存时 `PUT /api/profiles/` 提交到后端 | ✅ |
| `journey/page.tsx` | 重写为调用 `GET /api/journey/`，动态渲染节点完成状态和下一步推荐 | ✅ |

### 薪资 + 工资条接通

| 文件 | 改动 | 状态 |
|------|------|------|
| `salary/page.tsx` | 城市数据从 `GET /api/reports/salary/cities` 获取；薪资计算改为 `GET /api/reports/salary/calculate`（500ms debounce），保留本地计算降级 | ✅ |
| `payslip/page.tsx` | 调用 `POST /api/payslips/analyze`（500ms debounce），展示后端返回的核对结果和异常发现 | ✅ |

### Bug 修复

| 问题 | 修复 | 文件 |
|------|------|------|
| `Contract` 模型无 `case` relationship，`list_contracts` 运行时报错 | 改为 case_ids 子查询，与 offers 路由保持一致 | `app/api/routes/contracts.py` |
| preferences 页面跳转到 `/today` 而非报告页 | 修复为 `/offer/report` | `offer/preferences/page.tsx` |

### 设计决策

- **降级策略**：所有 API 调用都有 try/catch 降级，后端不可用时页面不崩溃
- **debounce**：salary 和 payslip 页面的实时计算使用 500ms debounce 避免频繁请求
- **状态持久化**：offer store 和 contract store 使用 zustand persist 中间件，刷新页面不丢失数据
- **前端仍保留本地计算能力**：salary 和 payslip 页面在后端不可用时可回退到前端计算

### 验证结果

- 前端 `npm run build` ✅ 通过，21 个路由全部正常
- 后端 `uvicorn app.main:app` ✅ 启动成功
- 后端 `/api/health` ✅ 正常
- 后端 `/api/auth/demo` ✅ 返回 JWT token
- 后端 profiles/cases/offers/contracts/journey/reports/payslips ✅ 全部 200

### 已知问题

- 后端 `rules/` 目录为空，合同审查规则内嵌在 `contract_review_service.py` 中（不影响功能）
- Redis 和 httpx 在 requirements.txt 中但代码未使用（不影响功能）
- 图片 OCR 仅支持 PyMuPDF 文本层，完整 OCR 需接入 Tesseract

---

## Sprint 6 补充 ✅ — 薪资计算器升级 + 财务规划页面

**完成时间**：2026-07-17

### 薪资计算器升级

#### 后端 `calculator_service.py` 新增计算因素

| 因素 | 说明 |
|------|------|
| 绩效工资 | 单独字段，参与社保基数和总收入 |
| 4项补贴 | 餐补/交通/住房/通讯，计入税前收入 |
| 社保基数自定义 | 实际薪资/基本月薪/自定义三选一 |
| 补充公积金 | 可选 0~5% |
| 补充医疗保险 | 可选 ¥0~500/月 |
| 年终奖 + 计税优化 | 自动对比单独/合并计税，推荐省税方案 |
| 真实年包 | 年到手 + 公积金双边（隐藏资产） |
| 储蓄率 | 月结余/月到手 |

#### 前端 `salary/page.tsx` 重写

- 左右分栏布局（输入 2/5 + 结果 3/5）
- 公积金/补充公积金改为滑块控件（5~12%、0~5%）
- 社保基数改为三选一卡片（实际薪资/基本月薪/自定义）
- 专项附加扣除改为滑块（0~5000）
- 补充医疗保险滑块（¥0~500）
- 年终奖计税优化卡片（单独 vs 合并对比）
- 7 项生活成本条形图

### 新建财务规划页面 `/finance`

#### 后端新增文件

| 文件 | 说明 |
|------|------|
| `app/services/finance_service.py` | 财务规划计算引擎（养老金/医保退休/公积金账户） |
| `app/api/routes/finance.py` | 3 个 API 端点：`/api/finance/pension`、`/medical`、`/housing-fund` |

#### 养老金估算

- 逐年模拟缴费过程（工资增长 + 社平工资增长 + 记账利息）
- 基础养老金 + 个人账户养老金双轨计算
- 替代率、回本周期分析
- 最低缴费年限政策（2030 起逐步提高到 20 年）

#### 医保退休待遇

- 10 城市医保最低缴费年限（男 20~30 年，女 15~25 年）
- 在职 vs 退休报销比例对比
- 退休后个人账户月入账 + 累计余额

#### 公积金账户

- 当前余额（含复利）
- 1/3/5/10 年增长预测
- 5 种提取场景说明（租房/购房/还贷/离职/退休）

#### 前端新增文件

| 文件 | 说明 |
|------|------|
| `src/app/(main)/finance/page.tsx` | 3 Tab 财务规划页（养老金/医保/公积金） |

#### 入口接入

| 文件 | 改动 |
|------|------|
| `tasks/page.tsx` | 新增"算算退休能领多少"入口 → `/finance` |
| `journey/page.tsx` | nodeHrefMap 增加"财务规划" → `/finance` |
| `journey_service.py` | 旅程模板增加第 10 个节点"财务规划" |

### Bug 修复

| 问题 | 修复 | 文件 |
|------|------|------|
| tasks 页面重复 key `/salary` | "城市够不够花"改为指向 `/journey` | `tasks/page.tsx` |
| today 页面 `href: "#"` | 3 个快捷入口改为真实路由 | `today/page.tsx` |
| 重复 key `#` 警告 | `key={action.href}` → `key={action.label}` | `today/page.tsx` |
| Hydration mismatch（浏览器扩展注入属性） | `<body>` 加 `suppressHydrationWarning` | `layout.tsx` |

### 验证结果

- 前端 `npm run build` ✅ 通过，22 个路由全部正常（新增 /finance）
- 后端 `python -c "from app.main import app"` ✅ 加载成功
- 养老金计算 ✅ 25岁/15000/杭州/60退休 → ¥30,270/月，替代率 38%，回本 3.6 年
- 医保计算 ✅ 杭州男 → 最低 20 年，报销 88%
- 公积金计算 ✅ 月缴 3600/已缴 24 月 → 当前 ¥87,763，5 年后 ¥319,035

---

## Sprint 7 ✅ — 用户管理中心 + 权限系统 + Schema 完善

**完成时间**：2026-07-17

### 后端改动

| 文件 | 说明 | 状态 |
|------|------|------|
| `app/models/user.py` | 新增 `is_admin` 字段 | ✅ |
| `alembic/versions/61644e47fec4_*.py` | 迁移：users 表添加 is_admin 列 | ✅ |
| `app/api/deps.py` | 新增 `require_admin` 权限依赖 | ✅ |
| `app/schemas/contract.py` | 新建：合同相关 Schema | ✅ |
| `app/schemas/salary.py` | 新建：薪资计算 Schema | ✅ |
| `app/schemas/payslip.py` | 新建：工资条 Schema | ✅ |
| `app/schemas/finance.py` | 新建：财务规划 Schema | ✅ |
| `app/schemas/report.py` | 新建：报告/薪资计算结果 Schema | ✅ |
| `app/schemas/auth.py` | TokenResponse/UserResponse 增加 is_admin | ✅ |
| `app/api/routes/auth.py` | 重写：登录返回 is_admin + 数据删除 API + 管理员用户管理 API | ✅ |
| `app/api/routes/contracts.py` | 改用 Pydantic Schema | ✅ |
| `app/api/routes/reports.py` | 改用 Pydantic Schema | ✅ |
| `app/api/routes/finance.py` | 改用 Pydantic Schema | ✅ |
| `app/api/routes/payslips.py` | 改用 Pydantic Schema | ✅ |
| `app/api/routes/salary_calcs.py` | 改用 Pydantic Schema | ✅ |

### 新增 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| DELETE | `/api/auth/data` | 用户清空自己的业务数据 |
| DELETE | `/api/auth/account` | 用户删除自己的账号 |
| GET | `/api/auth/users` | 管理员：获取用户列表 |
| DELETE | `/api/auth/users/{user_id}` | 管理员：删除指定用户 |

### 前端改动

| 文件 | 说明 | 状态 |
|------|------|------|
| `src/stores/auth.ts` | 新增 `isAdmin` 状态，登录/恢复时读取 | ✅ |
| `src/components/layout/Navbar.tsx` | 新增"管理中心"导航，管理员显示"管理后台" | ✅ |
| `src/app/(main)/dashboard/page.tsx` | 新建：用户管理中心（Offer/薪资/合同/工资条 Tab） | ✅ |
| `src/app/(main)/admin/page.tsx` | 新建：管理员用户列表 + 删除 | ✅ |
| `src/app/(main)/profile/page.tsx` | 接入真实删除 API（清空数据 + 删除账号） | ✅ |

### 验证结果

- 前端 `npx tsc --noEmit` ✅ 通过
- 后端 `python -c "from app.main import app"` ✅ 加载成功
- Alembic 迁移 ✅ 执行成功

---

## Sprint 8 ✅ — 导航改造 + 合同审查规则引擎数据库化

**完成时间**：2026-07-17

### 导航改造

| 文件 | 改动 | 状态 |
|------|------|------|
| `src/components/layout/Navbar.tsx` | 移除导航栏中的"管理中心""管理后台"链接，改为右上角用户名悬浮下拉菜单 | ✅ |
| `src/lib/api.ts` | 新增 `api.patch()` 方法 | ✅ |

**下拉菜单内容**：
- 📊 管理中心 → `/dashboard`（所有用户可见）
- ⚙️ 管理后台 → `/admin`（仅管理员可见）
- 分隔线
- 🚪 退出登录

### 合同审查规则引擎数据库化

参考 `Reference/engineering-contract-ai-review` 的双层规则体系设计。

#### 后端新增文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `app/models/review_rule.py` | ReviewRule ORM 模型（review_rules 表） | ✅ |
| `app/schemas/review_rule.py` | 规则请求/响应 Schema | ✅ |
| `app/services/rule_engine_service.py` | 规则引擎：4 种匹配模式（keyword/regex/contains_any/contains_all） | ✅ |
| `app/services/review_rule_service.py` | 规则 CRUD 服务 | ✅ |
| `app/api/routes/review_rules.py` | 规则管理 API（GET/POST/PATCH，管理员权限） | ✅ |
| `alembic/versions/a31f5740d0c5_*.py` | 建表迁移 + 8 条种子规则 | ✅ |

#### 后端修改文件

| 文件 | 改动 | 状态 |
|------|------|------|
| `app/services/contract_review_service.py` | `review_contract()` 增加 `db` 参数，双层规则：数据库规则优先 + 内置兜底，按 code 去重 | ✅ |
| `app/api/routes/contracts.py` | 审查和清单端点传入 `db` session | ✅ |
| `app/main.py` | 注册 review_rules 路由 | ✅ |
| `alembic/env.py` | 导入 ReviewRule 模型 | ✅ |

#### 前端修改文件

| 文件 | 改动 | 状态 |
|------|------|------|
| `src/app/(main)/admin/page.tsx` | 重写：增加 Tab 切换（用户管理/审查规则），规则管理支持 CRUD + 启用/停用 | ✅ |

### 新增 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/review-rules` | 获取规则列表（管理员） |
| POST | `/api/review-rules` | 创建规则（管理员） |
| PATCH | `/api/review-rules/{id}` | 更新规则（管理员） |

### 双层规则体系设计

1. **数据库规则**（管理员可增删改查）：存储在 `review_rules` 表，支持 4 种匹配模式，按优先级排序
2. **内置兜底规则**（代码常量）：8 条硬编码规则，当数据库不可用时仍能工作
3. **合并去重**：数据库规则优先执行，内置规则补充，按 `rule_code` 去重

### 验证结果

- 前端 `npx tsc --noEmit` ✅ 通过
- 后端 `python -c "from app.main import app"` ✅ 加载成功
- Alembic 迁移 ✅ 执行成功（review_rules 表 + 8 条种子数据）

---

## Sprint 9 ✅ — 全流程陪伴体验升级（导航扩展 + 知识学堂 + 旅程地图）

**完成时间**：2026-07-18

### 改动背景

用户反馈导航栏只有 4 个入口显得工作量不够，且缺少全流程陪伴感。本次升级将导航扩展到 6 项，新增知识学堂浏览页，新增 12 篇科普文章覆盖 6 个旅程阶段，并将旅程页从 10 节点线性时间线重构为 6 阶段 28 话题的完整地图。

### 导航栏扩展

| 文件 | 改动 | 状态 |
|------|------|------|
| `src/components/layout/Navbar.tsx` | 从 4 项扩展到 6 项：今天 / 一起看看 / 薪资工具 / 知识学堂 / 我的旅程 / 我的档案 | ✅ |

### 知识学堂浏览页

| 文件 | 说明 | 状态 |
|------|------|------|
| `src/app/(main)/knowledge/page.tsx` | **新建**：知识学堂浏览页，按分类分组展示文章，支持搜索和分类筛选，点击打开 ArticleDrawer | ✅ |

### 后端知识库扩展

| 文件 | 改动 | 状态 |
|------|------|------|
| `app/services/knowledge_service.py` | 新增 12 篇科普文章，总计 27 篇 | ✅ |

**新增文章清单**：

| slug | 标题 | 分类 |
|------|------|------|
| `shixi-value` | 我应该去实习吗 | 在校阶段 |
| `qiuzhi-guide` | 求职渠道与时间线 | 在校阶段 |
| `mianshi-guide` | 面试准备指南 | 求职阶段 |
| `offer-xuanze` | 两个 Offer 怎么选 | 求职阶段 |
| `xieyi-vs-hetong` | 实习协议 vs 三方 vs 劳动合同 | 签约阶段 |
| `shiyongqi-guize` | 试用期规则全解 | 签约阶段 |
| `weiyue-jin` | 违约金和竞业限制 | 签约阶段 |
| `ruzhi-checklist` | 入职第一周清单 | 入职阶段 |
| `chengshi-shengcun` | 新城市生存指南 | 入职阶段 |
| `zanqian-plan` | 攒钱计划 | 理财阶段 |
| `shebao-zhuanyi` | 社保转移指南 | 跳槽成长 |
| `tanxin-strategy` | 谈薪策略 | 跳槽成长 |
| `maifang-decision` | 买房决策指南 | 跳槽成长 |

### 旅程地图重构

| 文件 | 改动 | 状态 |
|------|------|------|
| `app/services/journey_service.py` | 重写：新增 6 阶段旅程地图数据结构（`JOURNEY_STAGES`），保留旧线性模板向后兼容 | ✅ |
| `app/api/routes/journey.py` | 更新：`GET /api/journey/` 返回 6 阶段地图数据 + 线性时间线数据 | ✅ |
| `src/app/(main)/journey/page.tsx` | 重写：从 10 节点线性时间线改为 6 阶段 28 话题可视化地图 | ✅ |

**6 阶段话题分布**：

| 阶段 | 话题数 | 文章 | 工具 |
|------|--------|------|------|
| 📚 在校阶段 | 5 | 4 | 1 |
| 🔍 求职阶段 | 5 | 3 | 2 |
| 📝 签约阶段 | 4 | 2 | 2 |
| 🏙️ 入职阶段 | 6 | 3 | 3 |
| 💰 理财阶段 | 4 | 2 | 2 |
| 🔄 跳槽/成长 | 4 | 4 | 0 |

### 验证结果

- 前端 `npm run build` ✅ 通过，23 个路由（新增 /knowledge）
- 前端 `npx tsc --noEmit` ✅ 通过
- 后端 `python -c "from app.main import app"` ✅ 加载成功
- 后端文章总数 ✅ 27 篇
- 后端旅程阶段 ✅ 6 阶段 28 话题

---

## Sprint 10 ✅ — 角色专场导航改造

**完成时间**：2026-07-18

### 改动背景

用户反馈希望导航从"功能视角"改为"角色视角"，让用户一进来就看到"这是为我准备的"。

### 导航改造

| 文件 | 改动 | 状态 |
|------|------|------|
| `src/components/layout/Navbar.tsx` | 重写：专场下拉菜单（4 个角色）+ 知识学堂 + 我的旅程 + 我的档案 | ✅ |

**导航结构**：
```
🛡️ 职护 | 🎯 专场▼ | 📚 知识学堂 | 🗺️ 我的旅程 | 👤 我的档案 | 用户名▼
```

**专场下拉菜单**：
- 🎓 实习生专场 — 从找实习到签协议，不再迷茫
- 🔍 找工作专场 — 从投简历到选 Offer，陪你做决定
- 🎯 应届生专场 — 合同条款、试用期、签约清单，一个都不漏
- 💼 在职专场 — 工资条、五险一金、攒钱计划，心里有数

### 角色专场页

| 文件 | 说明 | 状态 |
|------|------|------|
| `src/lib/personas.ts` | **新建**：4 个角色配置数据（工具/文章/旅程/提示） | ✅ |
| `src/app/(main)/persona/[id]/page.tsx` | **新建**：角色专场页模板（Hero + 工具入口 + 推荐阅读 + 旅程节点 + 专属提示） | ✅ |

**每个专场页包含**：
1. **Hero 区域**：角色专属标题和引导语，渐变色背景
2. **马上用**：3 个最相关的工具入口卡片
3. **推荐阅读**：4~5 篇精选文章（点击打开 ArticleDrawer）
4. **关键节点**：该角色的旅程时间线（文章/工具混合）
5. **💡 你知道吗**：角色专属的实用提醒
6. **切换专场**：底部其他专场快捷入口

### 首页专场引导

| 文件 | 改动 | 状态 |
|------|------|------|
| `src/app/(main)/today/page.tsx` | 在 Hero 和"职护能做什么"之间插入"你现在走到哪一步了？"专场选择区 | ✅ |

### 角色与 career_stage 映射

| career_stage | 默认专场 |
|-------------|---------|
| student | 实习生专场 |
| intern | 实习生专场 |
| jobseeking | 找工作专场 |
| offer | 应届生专场 |
| working | 在职专场 |

### 验证结果

- 前端 `npm run build` ✅ 通过，24 个路由（新增动态路由 /persona/[id]）
- 前端 `npx tsc --noEmit` ✅ 通过
