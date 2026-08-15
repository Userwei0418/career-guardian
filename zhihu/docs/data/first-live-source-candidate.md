# FP-02 首个真实来源候选：中国人保官方招聘

- 记录日期：2026-08-15
- 当前状态：`candidate / terms_review_pending / disabled`
- 当前操作：仅代码与公开页面只读调查，未调用招聘 API，未写入线上数据

## 为什么作为首选

1. [中国人保集团官网](https://www.picc.com.cn/?isfromportal=1) 的“人才招聘”入口直接链接到 `picc.zhiye.com`，来源归属比较清晰。
2. [中国人保招聘主页](https://picc.zhiye.com/custom/index2024?hideAll=true) 和公开岗位详情页不要求用户登录。
3. Pin 已有该来源的结构化 POST 请求与字段经验，不需要复用 Pin 的文件落地和 Core 直写链路。
4. 候选请求被限制为一页、一条记录，首次等待 10 秒，最多重试 1 次，只写 `market_raw`。

## 候选配置

- 站点：`picc.zhiye.com`
- 接口：`/api/Jobad/GetJobAdPageList`
- 方法：POST
- 范围：第 0 页，`PageSize=1`
- 传输：HTTPS，不使用 Cookie、账号、代理、验证码或浏览器规避
- 落库：仅 Raw 快照、任务状态和日志，不写 Core

## 未通过的合规门

当前公开页面能证明该招聘站与中国人保官网的链接关系，但本次只读检索没有取得可核验的数据批量获取授权声明。因此：

- `terms_review_status` 继续为 `pending`。
- `enabled` 继续为 `false`。
- 未得到人工确认前，任何真实请求都必须被系统拒绝并且不得写入 Raw。

## 人工确认语句

如决定将它作为 FP-02 的代表性真实来源，需要确认：

> 授权职护对中国人保公开招聘 API 执行一次、一条的低频验证请求，数据仅用于职护市场 Raw 链路技术验收，不对外分发，不直接进入 Core。
