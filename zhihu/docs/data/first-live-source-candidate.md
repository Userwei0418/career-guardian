# FP-02 首个真实来源候选：中国人保官方招聘

- 记录日期：2026-08-15
- 当前状态：`configured / terms_review_pending / disabled`
- 当前操作：仅代码与公开页面只读调查，未调用招聘 API，未写入线上数据

## 为什么作为首选

1. [中国人保集团官网](https://www.picc.com.cn/?isfromportal=1) 的“人才招聘”入口直接链接到 `picc.zhiye.com`，来源归属比较清晰。
2. [中国人保招聘主页](https://picc.zhiye.com/custom/index2024?hideAll=true) 和公开岗位详情页不要求用户登录。
3. Pin 已有该来源的结构化 POST 请求与字段经验，不需要复用 Pin 的文件落地和 Core 直写链路。
4. 已分别建立校园、实习和社招三个来源配置，使用可审计分页、页间限速和最多重试 1 次的独立任务执行。

## 候选配置

- 站点：`picc.zhiye.com`
- 接口：`/api/Jobad/GetJobAdPageList`
- 方法：POST
- 范围：从第 0 页开始，`PageSize=100`，最多 20 页；根据 `Count` 或短页停止
- 传输：HTTPS，不使用 Cookie、账号、代理、验证码或浏览器规避
- 落库：先写 Raw 快照、任务状态和日志；随后统一字段映射和质量门，只有通过项写入 `zhihu.market_*`

## 未通过的合规门

当前公开页面能证明该招聘站与中国人保官网的链接关系，但本次只读检索没有取得可核验的数据批量获取授权声明。因此：

- `terms_review_status` 继续为 `pending`。
- `enabled` 继续为 `false`。
- 未得到人工确认前，任何真实请求都必须被系统拒绝并且不得写入 Raw。

## 人工确认语句

如决定将它作为 FP-02 的代表性真实来源，需要确认：

> 授权职护对中国人保公开招聘 API 按页面已配置的上限和限速执行采集；原始数据仅进入 `market_raw`，只有通过统一质量门的岗位事实才进入 `zhihu.market_*` 并用于机会守护。
