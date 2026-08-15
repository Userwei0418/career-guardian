# 职护 AI 配置说明

- 生效日期：2026-08-15
- 配置位置：`zhihu/zhihu-backend/.env`
- 代码入口：`app/core/config.py`、`app/services/assistant_service.py`

## 当前运行配置

当前本地运行环境使用 OpenAI 兼容接口：

```text
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=deepseek-v4-flash
LLM_API_KEY=已配置，仅保存在本机 .env，不进入仓库、前端或接口响应
```

业务后端最终请求 `${LLM_BASE_URL}/chat/completions`，使用 `Authorization: Bearer ...`、`temperature=0.1` 和 30 秒超时。

## 使用范围

- Offer 文本结构化抽取调用统一 `_call_llm`；AI 不可用时返回空结构，由用户手工填写。
- 岗位 JD—简历分析调用同一配置；AI 不可用、超时或返回非 JSON 时，明确降级为规则核对，不伪装成 AI 结论。
- 简历上传只解析和保存文字，不自动调用 AI。只有用户在岗位详情主动点击分析按钮后，当前简历文字和该岗位 JD 才会发送给配置的 AI 服务。

## 是否可配置

可以配置，但当前属于服务端环境配置，不是管理员后台的在线配置：

| 配置项 | 作用 | 修改方式 |
|---|---|---|
| `LLM_BASE_URL` | OpenAI 兼容服务基础地址 | 修改后端 `.env` |
| `LLM_API_KEY` | 服务端访问密钥 | 修改后端 `.env`，禁止提交 Git |
| `LLM_MODEL` | 所有当前 AI 功能共用的模型名 | 修改后端 `.env` |

修改后需要重启职护后端进程才能生效。目前不支持在管理后台热切换供应商、按功能选择不同模型、版本回滚或记录模型调用成本；后续若产品需要多模型治理，应增加独立的服务端 AI 配置与审计模块，不能把密钥下发到浏览器。
