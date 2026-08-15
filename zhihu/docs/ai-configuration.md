# 职护 AI 配置说明

- 生效日期：2026-08-16
- 管理入口：`管理后台 → AI 配置`
- 代码入口：`app/api/routes/ai_admin.py`、`app/services/ai_configuration_service.py`、`app/services/assistant_service.py`

## 默认配置基线

管理员配置应使用以下 OpenAI 兼容接口基线：

```text
provider=SenseAudio
base_url=https://api.senseaudio.cn/v1
LLM_MODEL=deepseek-v4-flash
API_KEY=由管理员配置，接口和页面只显示末四位
```

业务后端最终请求 `${base_url}/chat/completions`，使用 `Authorization: Bearer ...`、`temperature=0.1` 和 30 秒超时。

## 使用范围

- Offer 文本结构化抽取调用统一 `_call_llm`；AI 不可用时返回空结构，由用户手工填写。
- 岗位 JD—简历分析调用同一配置；AI 不可用、超时或返回非 JSON 时，明确降级为规则核对，不伪装成 AI 结论。
- 简历上传只解析和保存文字，不自动调用 AI。只有用户在岗位详情主动点击分析按钮后，当前简历文字和该岗位 JD 才会发送给配置的 AI 服务。

## 管理员配置规则

管理员可以在页面调整：

| 配置项 | 作用 | 修改方式 |
|---|---|---|
| 服务商名称 | 管理识别和调用记录归属 | 管理页面直接修改 |
| OpenAI 兼容基础地址 | Chat Completions 基础地址 | 仅允许服务端白名单中的 HTTPS 域名 |
| 模型 ID | 所有当前 AI 功能共用的模型 | 管理页面直接修改 |
| API Key | 服务端鉴权密钥 | 新建时必填，后续留空表示保留原 Key |
| 启用状态 | 控制是否允许 AI 调用 | 停用后业务明确降级 |

保存后立即对后续调用生效，无需重启。管理页面提供连接测试，以及近 30 天调用成功数、失败数和 Token 汇总。

## 密钥和数据边界

- 管理员配置保存在 `zhihu.ai_provider_settings`，API Key 使用 Fernet 加密，完整值不进入接口响应、前端状态或 Git。
- `AI_CONFIG_ENCRYPTION_KEY` 是生产环境推荐的独立加密根密钥；未配置时使用 `JWT_SECRET` 派生本地兼容密钥。
- `zhihu.ai_configuration_audits` 记录修改人、服务商、地址、模型、启停和是否更换 Key，不记录 Key 内容。
- `zhihu.ai_invocation_logs` 只记录功能、模型、成功失败、耗时和 Token，不记录 Prompt、简历、Offer 或模型回答。
- `.env` 中的 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 仅作为尚未建立管理员配置时的兼容回退；一旦数据库存在配置，就以管理员配置为准。
- 允许域名由服务端 `AI_ALLOWED_BASE_HOSTS` 控制，防止管理员测试功能被用于请求任意内网地址。
