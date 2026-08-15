# FP-01 API 契约

## 职业事件

| 方法 | 路径 | 结果 |
|---|---|---|
| `GET` | `/api/events/` | 当前用户的职业事件列表 |
| `POST` | `/api/events/` | 新建五域职业事件 |
| `GET` | `/api/events/{id}` | 返回事件、证据、结论、行动、决策和结果 |
| `POST` | `/api/events/{id}/evidence` | 添加一份证据 |
| `POST` | `/api/events/{id}/findings` | 添加一条守护结论 |
| `POST` | `/api/events/{id}/actions` | 添加一项用户待确认行动 |
| `POST` | `/api/events/{id}/decisions` | 记录用户决定 |
| `POST` | `/api/events/{id}/outcomes` | 记录实际结果 |
| `GET` | `/api/guardian/state` | 返回首要守护领域和五域真实状态 |

请求和响应的字段、枚举及格式以 FastAPI `/docs` 和 `/openapi.json` 中的 Pydantic schema 为可执行契约。

## 统一错误

HTTP 错误与请求校验错误统一返回：

```json
{
  "error": {
    "code": "validation_error",
    "message": "请求参数不正确",
    "status": 422,
    "fields": []
  }
}
```

`code` 是稳定的机器可读值，`message` 是可向用户展示的文本，`fields` 只在校验失败时返回。用户对他人资源的读写与资源不存在一样返回 `404/not_found`。

## 市场洞察响应

`SalaryInsightResponse` 为 FP-04 预留契约，FP-01 仅用脱敏 fixture 验证 schema，不接入 Pin 运行时。关键字段包括：

- `availability`：`available`、`insufficient_data` 或 `source_unavailable`。
- `sample_size`、`observed_from`、`observed_to`：样本与时间边界。
- `methodology_version`、`quality_grade`：口径版本与质量等级。
- `sources`：可回链的数据源引用。
- `unavailable_reason`：数据不可用时的明确原因。
